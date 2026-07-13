from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APIClient

from user_database.models import CustomUser
from .models import Opportunity

from datetime import timedelta


TEST_CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}


@override_settings(CACHES=TEST_CACHES)
class OpportunityEditWindowTests(TestCase):
    """Content edits are locked 12 hours after posting, but is_open
    (close/reopen) stays editable at any age."""

    def setUp(self):
        self.client = APIClient()
        self.enabler = CustomUser.objects.create_user(
            username='org', email='org@example.com',
            password='Pass123!', role='enabler',
            is_email_verified=True,
        )
        self.client.force_authenticate(user=self.enabler)
        self.opportunity = Opportunity.objects.create(
            title='Community Manager',
            opportunity_type='volunteering',
            description='Help us grow.',
            link='https://example.org/apply',
            created_by=self.enabler,
        )
        self.url = reverse('opportunity-detail', kwargs={'pk': self.opportunity.pk})

    def _age_opportunity(self, hours):
        Opportunity.objects.filter(pk=self.opportunity.pk).update(
            posted_at=timezone.now() - timedelta(hours=hours)
        )
        self.opportunity.refresh_from_db()

    def test_content_edit_allowed_within_window(self):
        response = self.client.patch(self.url, {'title': 'Senior Community Manager'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.title, 'Senior Community Manager')

    def test_content_edit_blocked_after_window(self):
        self._age_opportunity(hours=13)
        response = self.client.patch(self.url, {'title': 'Sneaky New Title'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.title, 'Community Manager')

    def test_close_and_reopen_allowed_after_window(self):
        self._age_opportunity(hours=13)

        close = self.client.patch(self.url, {'is_open': False}, format='json')
        self.assertEqual(close.status_code, 200)
        self.opportunity.refresh_from_db()
        self.assertFalse(self.opportunity.is_open)

        reopen = self.client.patch(self.url, {'is_open': True}, format='json')
        self.assertEqual(reopen.status_code, 200)
        self.opportunity.refresh_from_db()
        self.assertTrue(self.opportunity.is_open)

    def test_unchanged_content_with_is_open_toggle_allowed_after_window(self):
        """A PATCH that resends identical content alongside an is_open toggle
        must not be blocked — only actual content changes are."""
        self._age_opportunity(hours=13)
        response = self.client.patch(self.url, {
            'title': self.opportunity.title,
            'is_open': False,
        }, format='json')
        self.assertEqual(response.status_code, 200)

    def test_target_applicants_optional_on_create(self):
        list_url = reverse('opportunity-list')
        with_target = self.client.post(list_url, {
            'title': 'Designer', 'opportunity_type': 'contract',
            'description': 'Design things.', 'link': 'https://example.org/designer',
            'target_applicants': 25,
        }, format='json')
        self.assertEqual(with_target.status_code, 201)
        self.assertEqual(with_target.data['target_applicants'], 25)
        self.assertEqual(with_target.data['applications_count'], 0)

        without_target = self.client.post(list_url, {
            'title': 'Writer', 'opportunity_type': 'contract',
            'description': 'Write things.', 'link': 'https://example.org/writer',
        }, format='json')
        self.assertEqual(without_target.status_code, 201)
        self.assertIsNone(without_target.data['target_applicants'])

    def test_content_change_smuggled_with_is_open_blocked_after_window(self):
        self._age_opportunity(hours=13)
        response = self.client.patch(self.url, {
            'description': 'Totally new description',
            'is_open': False,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.description, 'Help us grow.')
