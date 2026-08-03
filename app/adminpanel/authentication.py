"""
Standalone JWT auth for AdminUser (PRD 8.1).

Deliberately not simplejwt: platform tokens carry token_type "access"/"refresh"
and a user_id claim resolved against CustomUser; admin tokens carry
"admin_access"/"admin_refresh" and an admin_id resolved against AdminUser.
Neither token type is accepted by the other stack.
"""

from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework import authentication, exceptions

from .models import AdminUser

ADMIN_ACCESS_LIFETIME = timedelta(hours=1)
ADMIN_REFRESH_LIFETIME = timedelta(hours=12)
ALGORITHM = 'HS256'


def _make_token(admin, token_type, lifetime):
    now = timezone.now()
    payload = {
        'token_type': token_type,
        'admin_id': str(admin.id),
        'email': admin.email,
        'iat': int(now.timestamp()),
        'exp': int((now + lifetime).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def issue_admin_tokens(admin):
    return {
        'access_token': _make_token(admin, 'admin_access', ADMIN_ACCESS_LIFETIME),
        'refresh_token': _make_token(admin, 'admin_refresh', ADMIN_REFRESH_LIFETIME),
    }


def decode_admin_token(raw_token, expected_type):
    try:
        payload = jwt.decode(raw_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise exceptions.AuthenticationFailed('Token has expired.')
    except jwt.InvalidTokenError:
        raise exceptions.AuthenticationFailed('Invalid token.')

    if payload.get('token_type') != expected_type:
        raise exceptions.AuthenticationFailed('Invalid token type.')
    return payload


def admin_from_payload(payload):
    try:
        admin = AdminUser.objects.get(id=payload.get('admin_id'))
    except (AdminUser.DoesNotExist, ValueError, TypeError):
        raise exceptions.AuthenticationFailed('Admin account not found.')
    if not admin.is_active:
        raise exceptions.AuthenticationFailed('Admin account is disabled.')
    return admin


class AdminJWTAuthentication(authentication.BaseAuthentication):
    """Authenticates requests carrying `Authorization: Bearer <admin_access token>`."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower() != b'bearer':
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed('Invalid Authorization header.')

        payload = decode_admin_token(header[1].decode(), 'admin_access')
        return (admin_from_payload(payload), None)

    def authenticate_header(self, request):
        return 'Bearer'
