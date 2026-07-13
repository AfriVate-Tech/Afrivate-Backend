import logging

from django.contrib.auth import get_user_model
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.db import transaction

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from user_database.models import CustomUser, EmailVerification
from user_database.serializers import (
    CustomUserRegistrationSerializer,
    CustomUserLoginSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer,
    VerifyRegistrationOTPSerializer,
    VerifyPasswordResetOTPSerializer,
    VerifyEmailSerializer,
    GoogleAuthSerializer,
    SetPasswordSerializer,
)

from .utils import sendotp_via_email, send_signup_otp_email, send_welcome_email

from datetime import timedelta

User = get_user_model()

# Create your views here.
def index(request):
    return HttpResponse("Welcome to Afrivate Technologies Backend Service")

# user registration view
class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = CustomUserRegistrationSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_register'  # maps to 'auth_register': '5/hour' in settings.py

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # Wrap user creation + OTP generation in one transaction so that if the
            # email send fails the user row is rolled back — no orphaned unverifiable accounts.
            with transaction.atomic():
                user = serializer.save()

                verification, otp = EmailVerification.create_otp_verification(
                    email=user.email,
                    verification_type='user_signup',
                    user=user,
                    expiry_minutes=10
                )
                send_signup_otp_email(user.email, otp, user.username)

        except Exception as e:
            logging.error(f"Registration failed: {e}")
            return Response(
                {"error": "Registration failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({
            "message": "User registered successfully. Please check your email for the OTP verification code.",
            "user": {
                "username": user.username,
                "email": user.email,
                "role": user.role
            }
        }, status=status.HTTP_201_CREATED)

# user login view
class LoginView(generics.GenericAPIView):
    serializer_class = CustomUserLoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_login'
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        # Serializer already authenticates the user; we double-check verification here
        # because an unverified user can technically pass password validation.
        if not user.is_email_verified:
            return Response({
                "error": "Account not verified. Please verify your email using the OTP sent to you."
            }, status=status.HTTP_403_FORBIDDEN)

        tokens = user.tokens()  # mints JWT pair with custom claims (role, email)
        logging.info(f"Generating tokens for user {user.id}")
        
        return Response({
            "message": "Login successful",
            "user": {
                "username": user.username,
                "email": user.email,
                "role": user.role,  
            },
            "refresh": tokens['refresh_token'],
            "access": tokens['access_token']
        }, status=status.HTTP_200_OK)
    
# password forgot view
class ForgotPasswordView(generics.GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_forgot_password'

    def post(self, request, *args, **kwargs):
        from django.utils import timezone


        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # send password reset email
        try:
            user = CustomUser.objects.get(email=email)

            verification, otp = EmailVerification.create_otp_verification(
                email=email,
                verification_type='password_reset',
                user=user,
                expiry_minutes=10
            )
            
            email_sent = sendotp_via_email(user.email, otp, user.username)
            
            if email_sent:
                logging.info(f"Password reset OTP sent to {email}")
                return Response({
                    "success": True,
                    "message": "If the email exists, a password reset code has been sent."
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "success": False,
                    "message": "Failed to send OTP. Please try again."
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except CustomUser.DoesNotExist:
            logging.warning(f"Password reset requested for non-existent email: {email}")

        return Response({"message": "If the email exists, a password reset code has been sent."}, status=status.HTTP_200_OK)
    
class VerifyPasswordResetOtpView(generics.GenericAPIView):
    serializer_class = VerifyPasswordResetOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_otp_verify'

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        verification = serializer.validated_data['verification']
        user = serializer.validated_data['user']

        # Rotate the verified OTP into a single-use reset token. The OTP itself
        # is consumed here, and ResetPasswordView only accepts this token — so
        # the reset is bound to this verified session, not just the user id.
        reset_token = verification.issue_reset_token()

        logging.info(f"Password reset OTP verified for {user.email}")

        return Response({
            "success": True,
            "message": "OTP verified. You may now reset your password.",
            "uid": user.pk,
            "token": reset_token,
        }, status=status.HTTP_200_OK)

# password reset view
class ResetPasswordView(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_password_reset'
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        # The reset is authorized solely by the single-use token issued at OTP
        # verification — never by uid, which is guessable.
        verification = EmailVerification.objects.filter(
            token=token,
            verification_type='password_reset',
            is_verified=True,
        ).select_related('user').first()

        if not verification or verification.user is None or verification.is_expired():
            return Response(
                {"error": "Invalid or expired reset token. Please restart the password reset process."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = verification.user

        with transaction.atomic():
            user.set_password(new_password)
            # Setting is_email_verified=True here fixes the unverified-user catch-22:
            # previously a user who had never verified their email could complete the
            # password reset flow but still couldn't log in. Completing the reset OTP
            # flow proves the user controls the inbox, so marking them verified is safe.
            user.is_email_verified = True
            user.save()

            # Consume every outstanding reset record for this user so neither
            # this token nor any older pending OTP can be replayed.
            EmailVerification.objects.filter(
                user=user,
                verification_type='password_reset',
            ).delete()

        logging.info(f"Password reset successfully for {user.email}")
        return Response(
            {"message": "Password reset successful. You can now login with your new password."},
            status=status.HTTP_200_OK
        )

# user change password view
class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_password_reset'

    def post(self, request, *args, **kwargs):
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
    
            user = request.user
            # new_password = serializer.validated_data['new_password']
            user.set_password(serializer.validated_data['new_password'])
            user.save()
    
            logging.info(f"Password changed successfully for user {user.id}")
            return Response(
                {"message": "Password changed successfully"}, 
                status=status.HTTP_200_OK
            )

# user logout view
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logging.info(f"User {request.user.id} is logging out.")
        try:
            refresh_token = request.data["refresh"]
            if not refresh_token:
                logging.error(f"Logout error for user {request.user.id}: No refresh token provided.")
                return Response({"error": "No refresh token provided"}, status=status.HTTP_400_BAD_REQUEST)
            
            token = RefreshToken(refresh_token)
            token.blacklist()

            logging.info(f"User logged out successfully: {request.user.id}")
            return Response({"message": "Logout successful"}, status=status.HTTP_205_RESET_CONTENT)
        
        except Exception as e:
            logging.error(f"Logout error for user {request.user.id}: {e}")
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

# user deletion view
class DeleteUserView(generics.DestroyAPIView):  
    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        user = request.user
        logging.info(f"User deletion requested for user {user.id}")
        user.delete()
        logging.info(f"User deleted successfully: {user.id}")
        return Response({"message": "User account deleted successfully"}, status=status.HTTP_200_OK)   

# otp verify view
class OtpVerifyView(generics.GenericAPIView):
    serializer_class = VerifyRegistrationOTPSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_otp_verify'
            
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get the verified user from serializer
        verification = serializer.validated_data['verification']
        user = serializer.validated_data['user']

        verification.mark_verified()

        user.is_email_verified = True
        user.save()

        logging.info(f"OTP verified successfully for user {user.email}")
        
        # Generate tokens
        tokens = user.tokens()
        
        return Response({
            "success": True,
            "message": "Email verified successfully.",
            "user": {
                "email": user.email,
                "username": user.username,
                "is_email_verified": user.is_email_verified
            },
            "refresh": str(tokens['refresh_token']),
            "access": str(tokens['access_token'])
        }, status=status.HTTP_200_OK)

# resend otp view
class ResendOtpView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_resend_otp'

    def post(self, request, *args, **kwargs):
        from django.utils import timezone

        email = request.data.get('email', '').lower().strip()

        if not email:
            return Response(
                {"error": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            # Don't reveal whether email exists
            return Response(
                {"message": "If this email is registered, a new OTP has been sent."}, 
                status=status.HTTP_200_OK
            )

        if user.is_email_verified:
            return Response(
                {"error": "This account is already verified."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        latest = EmailVerification.objects.filter(
            email=email,
            verification_type = 'user_signup',
            is_verified = False
        ).order_by('-created_at').first()

        MAX_RESENDS = 3 # things like this should ideally be in settings incase of changes
        COOLDOWN_MINUTES = 30

        if latest:
            if latest.resend_count >= MAX_RESENDS:
                if latest.last_resend_at:
                    cooldown_end = latest.last_resend_at + timedelta(minutes=COOLDOWN_MINUTES)
                    if timezone.now() < cooldown_end:
                        wait_minutes = int((cooldown_end - timezone.now()).seconds / 60) + 1
                        return Response({
                            "error": f"Too many OTP requests. Please wait {wait_minutes} minutes before trying again."
                        }, status=status.HTTP_429_TOO_MANY_REQUESTS)
                    else:
                        latest.resend_count = 0
                        latest.save()

        # Invalidate old OTPs
        EmailVerification.objects.filter(
            email=email,
            verification_type='user_signup',
            is_verified=False
        ).update(expires_at=timezone.now())  # expire them all

        verification, otp = EmailVerification.create_otp_verification(
            email=email,
            verification_type='user_signup',
            user=user,
            expiry_minutes=10
        )

        verification.resend_count = (latest.resend_count + 1) if latest else 1
        verification.last_resend_at = timezone.now()
        verification.save()

        send_signup_otp_email(email, otp, user.username)

        logging.info(f"OTP resent to {email}, resend count: {verification.resend_count}")

        return Response(
            {"message": "If this email is registered, a new OTP has been sent."}, 
            status=status.HTTP_200_OK
        )

# verify email view    
class VerifyEmailView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = VerifyEmailSerializer
    
    def get(self, request, *args, **kwargs):
        token = request.query_params.get('token')

        if not token:
            return HttpResponseRedirect(f"{settings.FRONTEND_URL}/verify-error?reason=no_token")
        
        serializer = self.get_serializer(data={'token': token})

        if serializer.is_valid():
            try:
                verification = serializer.verify()
                logging.info(f"Email verified successfully for {verification.email}")
                
                send_welcome_email(verification.email, verification.waitlist_email.name if hasattr(verification, 'waitlist_email') else "")
                
                return HttpResponseRedirect(f"{settings.FRONTEND_URL}/verify-success")
                
            except Exception as e:
                logging.error(f"Error verifying email: {str(e)}")
                return HttpResponseRedirect(f"{settings.FRONTEND_URL}/verify-error?reason=server_error")
            
        errors = serializer.errors.get('token', [])
        if any("already been used" in str(e) for e in errors):
            return HttpResponseRedirect(f"{settings.FRONTEND_URL}/verify-success?already_done=true")

        return HttpResponseRedirect(f"{settings.FRONTEND_URL}/verify-error?reason=invalid_token")
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            try:
                verification = serializer.verify()
                return Response({
                    'success': True,
                    'message': 'Email verified successfully!',
                    'email': verification.email
                }, status=status.HTTP_200_OK)
                
            except Exception as e:
                logging.error(f"Error verifying email: {str(e)}")
                return Response({
                    'success': False,
                    'message': 'An error occurred during verification'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': False,
            'message': serializer.errors.get('token', ['Invalid token'])[0]
        }, status=status.HTTP_400_BAD_REQUEST)

# Google Login
class GoogleLoginView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = GoogleAuthSerializer

    def post(self, request, role='pathfinder', *args, **kwargs):
        # role comes from the URL kwargs: /google/pathfinder/ or /google/enabler/.
        # Existing users who re-authenticate via Google keep their original role;
        # the URL role parameter is only applied when creating a brand-new user.
        if role not in ['pathfinder', 'enabler']:
            return Response(
                {"error": "Invalid role. Must be 'pathfinder' or 'enabler'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_data = serializer.get_user_data()
        email = user_data['email']

        try:
            # Existing user — log in without altering their stored role.
            user = User.objects.get(email=email)
            logging.info(f"Existing user logged in via Google: {email}")

        except User.DoesNotExist:
            username = user_data['username']

            # Google usernames (email prefix) can collide; suffix with an incrementing
            # counter until a unique username is found.
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            user = User.objects.create_user(
                email=email,
                username=username,
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                role=role,
                is_email_verified=True,  # Google vouches for the email — no OTP needed
                auth_provider='google',
            )
            logging.info(f"New user created via Google: {email} with role {role}")

        tokens = user.tokens()

        return Response({
            "message": "Google login successful.",
            "user": {
                "email": user.email,
                "username": user.username,
                "role": user.role,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_email_verified": user.is_email_verified,
            },
            "access": tokens['access_token'],
            "refresh": tokens['refresh_token'],
        }, status=status.HTTP_200_OK)

class SetPasswordView(generics.GenericAPIView):
    """Allows Google-authenticated users to set a password 
    so they can also use normal email/password login"""
    permission_classes = [IsAuthenticated]
    serializer_class = SetPasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.auth_provider = 'email'
        user.save()

        logging.info(f"Password set for Google user {user.email}")
        return Response(
            {"message": "Password set successfully. You can now login with email and password."},
            status=status.HTTP_200_OK
        )