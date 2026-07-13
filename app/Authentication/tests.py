from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APIClient

from user_database.models import CustomUser, EmailVerification

from datetime import timedelta


# Throttling uses the Redis cache in production; tests run against local memory
# so they don't need a Redis instance.
TEST_CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}


@override_settings(CACHES=TEST_CACHES)
class PasswordResetFlowTests(TestCase):
    """The reset endpoint must be authorized only by the single-use token
    issued at OTP verification — never by uid, and never more than once."""

    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username='jane', email='jane@example.com',
            password='OldPass123!', role='pathfinder',
            is_email_verified=True,
        )
        self.verify_url = reverse('accounts:verify-password-reset-otp')
        self.reset_url = reverse('accounts:reset-password')

    def _verified_reset_token(self):
        """Run the OTP-verify step and return the issued reset token."""
        verification, otp = EmailVerification.create_otp_verification(
            email=self.user.email,
            verification_type='password_reset',
            user=self.user,
        )
        response = self.client.post(
            self.verify_url, {'email': self.user.email, 'otp': otp}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_verify_otp_returns_single_use_token(self):
        data = self._verified_reset_token()
        self.assertIn('token', data)
        self.assertEqual(data['uid'], self.user.pk)
        # The OTP record was rotated: the original 6-digit code no longer exists.
        self.assertFalse(
            EmailVerification.objects.filter(token__regex=r'^\d{6}$').exists()
        )

    def test_reset_succeeds_with_token_and_consumes_it(self):
        token = self._verified_reset_token()['token']
        response = self.client.post(self.reset_url, {
            'token': token,
            'new_password': 'NewPass456!',
            'confirm_password': 'NewPass456!',
        }, format='json')
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456!'))

        # Replaying the same token must fail — it was consumed.
        replay = self.client.post(self.reset_url, {
            'token': token,
            'new_password': 'Hacked789!',
            'confirm_password': 'Hacked789!',
        }, format='json')
        self.assertEqual(replay.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456!'))

    def test_reset_rejects_uid_only_request(self):
        """A uid without a token must never authorize a reset, even when a
        historically verified reset record exists for that user."""
        self._verified_reset_token()  # user now has a verified reset record
        response = self.client.post(self.reset_url, {
            'uid': self.user.pk,
            'new_password': 'Hacked789!',
            'confirm_password': 'Hacked789!',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass123!'))

    def test_reset_rejects_expired_token(self):
        token = self._verified_reset_token()['token']
        EmailVerification.objects.filter(token=token).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        response = self.client.post(self.reset_url, {
            'token': token,
            'new_password': 'NewPass456!',
            'confirm_password': 'NewPass456!',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_reset_rejects_unverified_otp_as_token(self):
        """A raw, never-verified OTP must not work as a reset token."""
        verification, otp = EmailVerification.create_otp_verification(
            email=self.user.email,
            verification_type='password_reset',
            user=self.user,
        )
        response = self.client.post(self.reset_url, {
            'token': otp,
            'new_password': 'NewPass456!',
            'confirm_password': 'NewPass456!',
        }, format='json')
        self.assertEqual(response.status_code, 400)
