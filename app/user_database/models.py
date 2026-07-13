from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings
from django.core.validators import EmailValidator

from rest_framework_simplejwt.tokens import RefreshToken

import uuid
from datetime import timedelta

# Create your models here.
class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('enabler', 'Enabler'),
        ('pathfinder', 'Pathfinder'),
    )
    email = models.EmailField(unique=True, validators=[EmailValidator()], null=False, blank=False, db_index=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=False, default='pathfinder', db_index=True)
    # bio = models.TextField(blank=True, null=True)
    
    # verifying email
    is_email_verified = models.BooleanField(default=False)
    auth_provider = models.CharField(
        max_length=20,
        default='email',
        choices=(
            ('email', 'Email'),
            ('google', 'Google'),
        )
    )

    # Field to store the OTP secret key
    # # otp_secret_key = models.CharField(max_length=32, null=True, blank=True)
    # reset_password_otp = models.IntegerField(null=True, blank=True)
    # reset_password_otp_expiry = models.DateTimeField(null=True, blank=True)
    # reset_password_otp_used = models.BooleanField(default=False)

    # USERNAME_FIELD = 'email_or_username' # i cant do this in abstract user
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'role']

    def tokens(self):
        """somewhere in the jwt code, there is a table storing these code alongside the attached
        custom claims"""
        refresh = RefreshToken.for_user(self)

        # attach custom claims
        refresh['role'] = self.role
        refresh['email'] = self.email

        return {
            "refresh_token": str(refresh),
            "access_token": str(refresh.access_token),
        }

    def __str__(self):
        return self.username

class EmailVerification(models.Model):
    """Reusable email verification model for both waitlist and user registration"""
    VERIFICATION_TYPE_CHOICES = (
        ('waitlist', 'Waitlist'),
        ('user_signup', 'User Signup'),
        ('password_reset', 'Password Reset'),
        # ('email_change', 'Email Change')
    )

    #link to user if they exist (null for waitlist signups)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        null=True, blank=True)
    
    email = models.EmailField(
        validators=[EmailValidator()],
        null=False, blank=False,
        db_index=True)
    
    # can actually be a uuid for links or a 6-digit string for otps
    token = models.CharField(max_length=64, unique=True, db_index=True)

    verification_type = models.CharField(max_length=20, choices=VERIFICATION_TYPE_CHOICES)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    resend_count = models.IntegerField(default=0)
    last_resend_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.email} - {self.verification_type} - {'Verified' if self.is_verified else 'Pending'}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Email Verification'
        verbose_name_plural = 'Email Verifications' 

    @classmethod
    def create_verification(cls, email, verification_type, user=None, expiry_minutes=20):
        """Factory method to create a new verification token"""
        email = email.lower().strip()
        token = uuid.uuid4().hex # send this with the mail link
        expires_at = timezone.now() + timedelta(minutes=expiry_minutes)
        
        return cls.objects.create(
            email=email.lower().strip(),
            verification_type=verification_type,
            token=token,
            expires_at=expires_at,
            user=user
        )
    
    @classmethod
    def create_otp_verification(cls, email, verification_type, user=None, expiry_minutes=10):
        
        import random

        email = email.lower().strip()
        otp = str(random.randint(100000, 999999))
        expires_at = timezone.now() + timedelta(minutes=expiry_minutes)
        
        verification = cls.objects.create(
            email=email,
            verification_type=verification_type,
            token=otp,
            expires_at=expires_at,
            user=user
        )
        return verification, otp
    
    
    def is_valid(self):
        """Check if token is still valid (not expired and not already verified)"""
        if self.is_verified:
            return False
        return timezone.now() < self.expires_at

    def issue_reset_token(self, expiry_minutes=15):
        """Consume a verified OTP by rotating this record into a single-use
        password-reset token with its own short expiry window. The original
        OTP is destroyed in the process, so it cannot be replayed."""
        self.token = uuid.uuid4().hex
        self.is_verified = True
        self.verified_at = timezone.now()
        self.expires_at = timezone.now() + timedelta(minutes=expiry_minutes)
        self.save()
        return self.token
    
    def mark_used(self):
        """Mark as used"""
        self.is_verified = True
        self.save()
    
    def mark_verified(self):
        """Mark as verified"""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.save()
    
    def is_expired(self):
        """Check if token has expired"""
        return timezone.now() >= self.expires_at
