from django.http import HttpResponse
from django.db.models import Exists, OuterRef, Q
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


def health_check(request):
    return HttpResponse("Notifications service is running.")

class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer

    def get_permissions(self):
        # Any authenticated user may create (perform_create restricts
        # non-staff to addressed personal messages — no broadcasts).
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_staff:
            serializer.save()
            return
        # Non-staff (e.g. an enabler contacting an applicant) must address a
        # specific recipient and can only send personal notifications.
        if serializer.validated_data.get('recipient') is None:
            raise ValidationError({"recipient": "A recipient is required."})
        serializer.save(type='personal')

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()

        user = self.request.user

        if user.is_authenticated:
            # recipient=user → personal notification for this user only
            # recipient=null → broadcast visible to all authenticated users
            # current_user_read is annotated as a subquery so the serializer can read
            # it as a plain attribute without triggering additional DB queries per row.
            return Notification.objects.filter(
                Q(recipient=user) | Q(recipient__isnull=True)
            ).annotate(
                current_user_read=Exists(
                    Notification.read_by.through.objects.filter(
                        notification_id=OuterRef('pk'),
                        customuser_id=user.id
                    )
                )
            ).order_by('-created_at')

        # Unauthenticated path is a fallback; in practice all list views require auth.
        return Notification.objects.filter(recipient__isnull=True).order_by('-created_at')

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.read_by.add(request.user)
        return Response(
            {"message": "Notification marked as read."},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def mark_all_read(self, request):
        user = request.user
        unread_notifications = Notification.objects.filter(
            Q(recipient=user) | Q(recipient__isnull=True)
        ).exclude(read_by=user)
        count = unread_notifications.count()

        if unread_notifications.exists():
            request.user.read_notifications.add(*unread_notifications)

        return Response(
            {"message": f"{count} notifications marked as read."},
            status=status.HTTP_200_OK
        )
