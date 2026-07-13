from django.test import TestCase, override_settings

from rest_framework.test import APIClient

from user_database.models import CustomUser
from .models import Notification


TEST_CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}


@override_settings(CACHES=TEST_CACHES)
class NotificationCreateTests(TestCase):
    """Non-staff users may only send addressed personal notifications
    (the enabler 'Contact pathfinder' flow); broadcasts stay admin-only."""

    def setUp(self):
        self.client = APIClient()
        self.enabler = CustomUser.objects.create_user(
            username='org', email='org@example.com', password='Pass123!',
            role='enabler', is_email_verified=True,
        )
        self.pathfinder = CustomUser.objects.create_user(
            username='jane', email='jane@example.com', password='Pass123!',
            role='pathfinder', is_email_verified=True,
        )

    def test_enabler_can_send_personal_notification(self):
        self.client.force_authenticate(user=self.enabler)
        response = self.client.post('/api/notify/notifications/', {
            'title': 'Interview invite',
            'message': 'We would like to talk to you.',
            'priority': 'info',
            'type': 'personal',
            'recipient': self.pathfinder.id,
        }, format='json')
        self.assertEqual(response.status_code, 201)

        note = Notification.objects.get()
        self.assertEqual(note.recipient_id, self.pathfinder.id)
        self.assertEqual(note.type, 'personal')

        # The recipient sees it in their list; the sender does not.
        self.client.force_authenticate(user=self.pathfinder)
        listed = self.client.get('/api/notify/notifications/')
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]['title'], 'Interview invite')

        self.client.force_authenticate(user=self.enabler)
        sender_list = self.client.get('/api/notify/notifications/')
        self.assertEqual(len(sender_list.data), 0)

    def test_non_staff_cannot_broadcast(self):
        """Creating without a recipient (a broadcast) stays staff-only."""
        self.client.force_authenticate(user=self.enabler)
        response = self.client.post('/api/notify/notifications/', {
            'title': 'Spam', 'message': 'Everyone look at me',
            'priority': 'info', 'type': 'system',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Notification.objects.count(), 0)

    def test_non_staff_type_forced_to_personal(self):
        self.client.force_authenticate(user=self.enabler)
        response = self.client.post('/api/notify/notifications/', {
            'title': 'Hello', 'message': 'Hi', 'priority': 'critical',
            'type': 'system', 'recipient': self.pathfinder.id,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Notification.objects.get().type, 'personal')

    def test_non_staff_cannot_update_or_delete(self):
        note = Notification.objects.create(
            title='Broadcast', message='For all', type='system', priority='info',
        )
        self.client.force_authenticate(user=self.enabler)
        self.assertEqual(
            self.client.patch(f'/api/notify/notifications/{note.id}/', {'title': 'x'}, format='json').status_code, 403
        )
        self.assertEqual(
            self.client.delete(f'/api/notify/notifications/{note.id}/').status_code, 403
        )
