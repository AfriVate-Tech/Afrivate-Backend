from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .authentication import (
    AdminJWTAuthentication,
    admin_from_payload,
    decode_admin_token,
    issue_admin_tokens,
)
from .permissions import IsAdminPanelUser
from .serializers import AdminLoginSerializer, AdminUserSerializer


class AdminLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'admin_login'

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        admin = serializer.validated_data['admin']

        admin.last_login = timezone.now()
        admin.save(update_fields=['last_login'])

        return Response({
            'admin': AdminUserSerializer(admin).data,
            **issue_admin_tokens(admin),
        })


class AdminTokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw = request.data.get('refresh_token')
        if not raw:
            return Response(
                {'detail': 'refresh_token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = decode_admin_token(raw, 'admin_refresh')
        admin = admin_from_payload(payload)
        return Response(issue_admin_tokens(admin))


class AdminMeView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminPanelUser]

    def get(self, request):
        return Response(AdminUserSerializer(request.user).data)
