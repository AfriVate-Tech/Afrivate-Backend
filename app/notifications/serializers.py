from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    current_user_read = serializers.SerializerMethodField()
    # Write-only: who the notification is addressed to. Omitted/null means a
    # broadcast, which only staff are allowed to create (enforced in the view).
    recipient = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    class Meta:
        model = Notification
        fields = ["id", "title", "message", "priority", "type", "link", "created_at", "current_user_read", "recipient"]

    def get_current_user_read(self, obj):
        return getattr(obj, 'current_user_read', False)