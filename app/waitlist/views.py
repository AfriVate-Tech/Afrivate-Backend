from django.shortcuts import render
from django.http import HttpResponse

from rest_framework import generics, status
from rest_framework.response import Response

from .serializers import WaitlistEmailSerializer, WaitlistStatsSerializer
import logging

from rest_framework.permissions import AllowAny, IsAdminUser
from .utils import send_welcome_email    


# Create your views here.
def index(request):
    return HttpResponse("Welcome to the Waitlist API")

# waitlist email view
class WaitlistEmailView(generics.GenericAPIView):
    """ waitlist email submissions!!"""
    serializer_class = WaitlistEmailSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            try:
                user = serializer.save()
                # no more verification for waitlist
                email_sent = send_welcome_email(user.email, user.name)
                if not email_sent:
                    logging.error(f"Failed to send email to {user.email}")
                

                # SEND CONFIRMATION EMAIL
                # email_sent = send_waitlist_verification_email(
                #     request,
                #     user.verification.token, 
                #     user.email)

                if email_sent:
                    return Response({
                        "success": True,
                        'message': "Successfully signed up for the waitlist!",
                        'email': user.email
                        },
                        status=status.HTTP_201_CREATED)
                else:
                    return Response({
                        'success': False,
                        'message': 'Failed to send welcome email. Please try again.'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
            except Exception as e:
                logging.error(f"Waitlist signup failed for email {request.data.get('email')}: {str(e)}", exc_info=True)
                
                return Response({
                   'success': False,
                   'message': ' An error occured. Please try again.' 
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        return Response({
            "success": False,
            'message': "Invalid data",
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    

# waitlist stats view
class WaitlistStatsView(generics.GenericAPIView):
    """Get waitlist statistics - Admin only"""
    serializer_class = WaitlistStatsSerializer
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer()
        stats = serializer.get_stats()
        
        return Response({
            'success': True,
            'data': stats
        }, status=status.HTTP_200_OK)
    
