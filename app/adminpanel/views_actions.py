from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from notifications.models import Notification
from user_database.models import CustomUser

from .emails import queue_email, send_admin_email, send_bulk_admin_email
from .models import AdminActionLog, BroadcastMessage
from .utils import filter_users, log_action
from .views_directory import AdminAPIView

# PRD 6.3.2 — the small set of fields an admin may correct on a user's behalf.
EDITABLE_USER_FIELDS = ('email', 'username')
EDITABLE_PROFILE_FIELDS = ('phone_number', 'contact_email', 'state', 'country', 'address')


def _get_platform_user(user_id):
    return get_object_or_404(CustomUser, id=user_id, is_superuser=False)


def _notify_in_app(user, subject, body):
    """The in-app half of dual-channel messaging (PRD 6.3.3): a brief posted
    to the recipient's notification page; the email carries the full message."""
    return Notification.objects.create(
        recipient=user,
        title=subject,
        message=body[:300],
        type='personal',
        priority='info',
    )


class SuspendUserView(AdminAPIView):
    """PRD 6.3.1 — suspend with a required, logged reason (not just a toggle)."""

    def post(self, request, user_id):
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response({'detail': 'A reason is required to suspend an account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        user = _get_platform_user(user_id)
        if user.is_suspended:
            return Response({'detail': 'Account is already suspended.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # is_active=False makes the existing login serializer reject the user.
        user.is_suspended = True
        user.is_active = False
        user.save(update_fields=['is_suspended', 'is_active'])

        log_action(request.user, AdminActionLog.ActionType.SUSPEND, user.role, user.id, reason)
        return Response({'detail': f'Account suspended.', 'user_id': user.id})


class ReinstateUserView(AdminAPIView):
    def post(self, request, user_id):
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response({'detail': 'A reason is required to reinstate an account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        user = _get_platform_user(user_id)
        if not user.is_suspended:
            return Response({'detail': 'Account is not suspended.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user.is_suspended = False
        user.is_active = True
        user.save(update_fields=['is_suspended', 'is_active'])

        log_action(request.user, AdminActionLog.ActionType.REINSTATE, user.role, user.id, reason)
        return Response({'detail': 'Account reinstated.', 'user_id': user.id})


class EditUserView(AdminAPIView):
    """PRD 6.3.2 — edit key fields on behalf of a user, logged against the admin."""

    def patch(self, request, user_id):
        user = _get_platform_user(user_id)
        profile = getattr(user, 'profile', None)
        changed = []

        for field in EDITABLE_USER_FIELDS:
            if field in request.data:
                new = (request.data[field] or '').strip()
                old = getattr(user, field)
                if new and new != old:
                    setattr(user, field, new)
                    changed.append(f"{field}: '{old}' -> '{new}'")

        profile_changed = []
        if profile:
            for field in EDITABLE_PROFILE_FIELDS:
                if field in request.data:
                    new = (request.data[field] or '').strip()
                    old = getattr(profile, field)
                    if new != (old or ''):
                        setattr(profile, field, new)
                        profile_changed.append(f"{field}: '{old}' -> '{new}'")

        if not changed and not profile_changed:
            return Response({'detail': 'No changes supplied.'}, status=status.HTTP_400_BAD_REQUEST)

        if changed:
            user.save()
        if profile_changed:
            profile.save()

        log_action(
            request.user, AdminActionLog.ActionType.EDIT_PROFILE, user.role, user.id,
            reason='; '.join(changed + profile_changed),
        )
        return Response({'detail': 'Profile updated.', 'changes': changed + profile_changed})


class MessageUserView(AdminAPIView):
    """PRD 6.3.3 (individual) — full email + in-app brief."""

    def post(self, request, user_id):
        subject = (request.data.get('subject') or '').strip()
        body = (request.data.get('body') or '').strip()
        if not subject or not body:
            return Response({'detail': 'subject and body are required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user = _get_platform_user(user_id)
        _notify_in_app(user, subject, body)
        emailed = queue_email(send_admin_email, user.email, subject, body)

        log_action(request.user, AdminActionLog.ActionType.SEND_MESSAGE, user.role, user.id,
                   reason=f'Subject: {subject}')
        detail = (
            f'Message sent to {user.email}.' if emailed
            else 'In-app notification posted, but the email queue is unavailable — email not sent.'
        )
        return Response({'detail': detail, 'email_queued': emailed})


class MessageSegmentView(AdminAPIView):
    """PRD 6.3.3 (bulk) / 6.6.2 — message a filtered segment, reusing the
    directory filter logic. Recorded as a custom_segment BroadcastMessage."""

    def post(self, request):
        subject = (request.data.get('subject') or '').strip()
        body = (request.data.get('body') or '').strip()
        filters = request.data.get('filters') or {}
        if not subject or not body:
            return Response({'detail': 'subject and body are required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        users = list(filter_users(filters))
        if not users:
            return Response({'detail': 'No users match this segment.'},
                            status=status.HTTP_400_BAD_REQUEST)

        Notification.objects.bulk_create([
            Notification(recipient=u, title=subject, message=body[:300],
                         type='personal', priority='info')
            for u in users
        ])
        emailed = queue_email(send_bulk_admin_email, [u.email for u in users], subject, body)

        broadcast = BroadcastMessage.objects.create(
            sent_by_admin=request.user,
            audience=BroadcastMessage.Audience.CUSTOM_SEGMENT,
            segment_filter=filters,
            subject=subject,
            message_body=body,
            recipient_count=len(users),
        )
        log_action(request.user, AdminActionLog.ActionType.SEND_MESSAGE, 'connection',
                   broadcast.id, reason=f'Segment message to {len(users)} users: {subject}')
        detail = (
            f'Message queued for {len(users)} users.' if emailed
            else f'In-app notifications posted for {len(users)} users, but the email queue is unavailable — emails not sent.'
        )
        return Response({'detail': detail, 'recipient_count': len(users), 'email_queued': emailed})


class ActionLogView(AdminAPIView):
    """PRD 8.3 — the audit trail, viewable in the dashboard."""

    def get(self, request):
        logs = AdminActionLog.objects.select_related('admin')[:200]
        return Response([
            {
                'id': log.id,
                'admin': log.admin.full_name,
                'action_type': log.action_type,
                'target_entity_type': log.target_entity_type,
                'target_entity_id': log.target_entity_id,
                'reason': log.reason,
                'created_at': log.created_at,
            }
            for log in logs
        ])
