from rest_framework import serializers

from applications.models import Application

from .models import AdminNote, AdminUser, BroadcastMessage
from .utils import account_status, display_name


class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        try:
            admin = AdminUser.objects.get(email=data['email'].lower().strip())
        except AdminUser.DoesNotExist:
            raise serializers.ValidationError('Invalid admin credentials.')
        if not admin.check_password(data['password']) or not admin.is_active:
            raise serializers.ValidationError('Invalid admin credentials.')
        data['admin'] = admin
        return data


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminUser
        fields = ['id', 'full_name', 'email', 'is_active', 'last_login', 'created_at']


class AdminNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author_admin.full_name', read_only=True)

    class Meta:
        model = AdminNote
        fields = ['id', 'entity_type', 'entity_id', 'note_text', 'author_name', 'created_at']
        read_only_fields = ['id', 'author_name', 'created_at']


class DirectoryRowSerializer(serializers.Serializer):
    """PRD 6.1.3 list columns: name, type, signup date, last active date, status."""

    id = serializers.IntegerField()
    name = serializers.SerializerMethodField()
    username = serializers.CharField()
    email = serializers.EmailField()
    type = serializers.CharField(source='role')
    signup_date = serializers.DateTimeField(source='date_joined')
    last_active = serializers.DateTimeField(source='last_login', allow_null=True)
    status = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()

    def get_name(self, user):
        return display_name(user)

    def get_status(self, user):
        return account_status(user)

    def get_state(self, user):
        profile = getattr(user, 'profile', None)
        return profile.state if profile else None


class ConnectionSerializer(serializers.ModelSerializer):
    """PRD 6.4.2 — which Pathfinder, which Enabler, what role/opportunity,
    when it started, current status."""

    pathfinder_id = serializers.IntegerField(source='user.id', read_only=True)
    pathfinder_name = serializers.SerializerMethodField()
    pathfinder_email = serializers.EmailField(source='user.email', read_only=True)
    enabler_id = serializers.IntegerField(source='opportunity.created_by.id', read_only=True)
    enabler_name = serializers.SerializerMethodField()
    opportunity_id = serializers.IntegerField(source='opportunity.id', read_only=True)
    opportunity_title = serializers.CharField(source='opportunity.title', read_only=True)
    opportunity_type = serializers.CharField(source='opportunity.opportunity_type', read_only=True)

    class Meta:
        model = Application
        fields = [
            'id', 'status', 'applied_at', 'reviewed_at',
            'pathfinder_id', 'pathfinder_name', 'pathfinder_email',
            'enabler_id', 'enabler_name',
            'opportunity_id', 'opportunity_title', 'opportunity_type',
        ]
        read_only_fields = [f for f in fields if f != 'status']

    def get_pathfinder_name(self, obj):
        return display_name(obj.user)

    def get_enabler_name(self, obj):
        return display_name(obj.opportunity.created_by)


class BroadcastMessageSerializer(serializers.ModelSerializer):
    sent_by = serializers.CharField(source='sent_by_admin.full_name', read_only=True)

    class Meta:
        model = BroadcastMessage
        fields = [
            'id', 'audience', 'segment_filter', 'subject', 'message_body',
            'recipient_count', 'sent_by', 'sent_at',
        ]
        read_only_fields = ['id', 'recipient_count', 'sent_by', 'sent_at']
