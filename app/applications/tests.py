from django.test import TestCase, override_settings

from rest_framework.test import APIClient

import cloudinary

from user_database.models import CustomUser
from opportunities.models import Opportunity
from profiles.models import Credential


TEST_CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}


@override_settings(CACHES=TEST_CACHES)
class ApplicationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Signed-URL generation needs Cloudinary credentials configured;
        # dummy values suffice — URL building is purely local.
        cloudinary.config(cloud_name='test', api_key='test-key', api_secret='test-secret')

    def setUp(self):
        self.client = APIClient()
        self.enabler_user = CustomUser.objects.create_user(
            username='org', email='org@example.com', password='Pass123!',
            role='enabler', is_email_verified=True,
        )
        self.pathfinder_user = CustomUser.objects.create_user(
            username='jane', email='jane@example.com', password='Pass123!',
            role='pathfinder', is_email_verified=True,
        )
        self.other_pathfinder = CustomUser.objects.create_user(
            username='eve', email='eve@example.com', password='Pass123!',
            role='pathfinder', is_email_verified=True,
        )
        self.opp = Opportunity.objects.create(
            title='Junior Editor', opportunity_type='contract',
            description='Edit things.', link='https://example.org/editor',
            created_by=self.enabler_user,
        )

    def test_enabler_cannot_apply(self):
        """Checks that an Enabler cannot apply for an opportunity."""
        self.client.force_authenticate(user=self.enabler_user)
        response = self.client.post('/api/applications/', {'opportunity': self.opp.id, 'cover_letter': 'Hi'})
        self.assertEqual(response.status_code, 403)

    def test_duplicate_application_fails(self):
        """Checks that a Pathfinder cannot apply twice."""
        self.client.force_authenticate(user=self.pathfinder_user)
        first = self.client.post('/api/applications/', {'opportunity': self.opp.id, 'cover_letter': 'Hi'})
        self.assertEqual(first.status_code, 201)
        response = self.client.post('/api/applications/', {'opportunity': self.opp.id, 'cover_letter': 'Hi again'})
        self.assertEqual(response.status_code, 400)
        self.assertIn("already applied", str(response.data))

    def test_apply_with_own_profile_resume(self):
        """A pathfinder can attach their own profile credential as resume."""
        cred = Credential.objects.create(
            profile=self.pathfinder_user.profile,
            document_name='My Resume', document='credentials/jane-resume.pdf',
        )
        self.client.force_authenticate(user=self.pathfinder_user)
        response = self.client.post('/api/applications/', {
            'opportunity': self.opp.id, 'cover_letter': 'Hi', 'profile_resume': cred.id,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['profile_resume'], cred.id)

    def test_cannot_attach_someone_elses_credential(self):
        """profile_resume must belong to the applicant — no IDOR on documents."""
        other_cred = Credential.objects.create(
            profile=self.other_pathfinder.profile,
            document_name='Eve Private Doc', document='credentials/eve-doc.pdf',
        )
        self.client.force_authenticate(user=self.pathfinder_user)
        response = self.client.post('/api/applications/', {
            'opportunity': self.opp.id, 'cover_letter': 'Hi', 'profile_resume': other_cred.id,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('profile_resume', response.data)
