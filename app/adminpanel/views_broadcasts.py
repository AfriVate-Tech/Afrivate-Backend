from rest_framework import status
from rest_framework.response import Response

from notifications.models import Notification
from user_database.models import CustomUser

from .emails import queue_email, send_bulk_admin_email
from .models import BroadcastMessage
from .serializers import BroadcastMessageSerializer
from .views_directory import AdminAPIView


class BroadcastView(AdminAPIView):
    """PRD 6.6 — broadcast to all Pathfinders, all Enablers, or both, via
    email + in-app notification, with a log of past broadcasts."""

    def get(self, request):
        broadcasts = BroadcastMessage.objects.select_related('sent_by_admin')[:100]
        return Response(BroadcastMessageSerializer(broadcasts, many=True).data)

    def post(self, request):
        audience = request.data.get('audience')
        subject = (request.data.get('subject') or '').strip()
        body = (request.data.get('body') or '').strip()

        valid_audiences = (
            BroadcastMessage.Audience.ALL_PATHFINDERS,
            BroadcastMessage.Audience.ALL_ENABLERS,
            BroadcastMessage.Audience.ALL_USERS,
        )
        if audience not in valid_audiences:
            return Response(
                {'detail': f'audience must be one of {[a.value for a in valid_audiences]}. '
                           'For filtered segments use /api/admin/messages/segment/.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not subject or not body:
            return Response({'detail': 'subject and body are required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        recipients = CustomUser.objects.filter(is_superuser=False, is_suspended=False)
        if audience == BroadcastMessage.Audience.ALL_PATHFINDERS:
            recipients = recipients.filter(role='pathfinder')
        elif audience == BroadcastMessage.Audience.ALL_ENABLERS:
            recipients = recipients.filter(role='enabler')
        recipients = list(recipients)

        if audience == BroadcastMessage.Audience.ALL_USERS:
            # recipient=null is an all-users broadcast in the existing model
            Notification.objects.create(
                title=subject, message=body[:300], type='system', priority='info',
            )
        else:
            # Role-targeted: fan out personal rows, since null-recipient
            # broadcasts are visible to every user regardless of role.
            Notification.objects.bulk_create([
                Notification(recipient=u, title=subject, message=body[:300],
                             type='system', priority='info')
                for u in recipients
            ])

        emailed = queue_email(send_bulk_admin_email, [u.email for u in recipients], subject, body)

        broadcast = BroadcastMessage.objects.create(
            sent_by_admin=request.user,
            audience=audience,
            subject=subject,
            message_body=body,
            recipient_count=len(recipients),
        )
        data = BroadcastMessageSerializer(broadcast).data
        data['email_queued'] = emailed
        if not emailed:
            data['detail'] = ('In-app notifications posted, but the email queue is '
                              'unavailable — emails not sent.')
        return Response(data, status=status.HTTP_201_CREATED)
