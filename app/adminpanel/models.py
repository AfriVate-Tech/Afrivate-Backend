"""
Admin Dashboard models — see AfriVate Admin Dashboard PRD, Section 7.

AdminUser is deliberately a separate model from CustomUser (PRD 8.1): admin
authentication never touches the Pathfinder/Enabler auth stack, so a platform
JWT can never reach an admin route and vice versa.
"""

import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import EmailValidator
from django.db import models


class AdminUser(models.Model):
    """PRD 7.1 — single equal-access admin role for this phase (no `role` field)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True, validators=[EmailValidator()], db_index=True)
    password = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Admin User'

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    # DRF expects these on request.user
    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False


class EntityType(models.TextChoices):
    PATHFINDER = 'pathfinder', 'Pathfinder'
    ENABLER = 'enabler', 'Enabler'
    CONNECTION = 'connection', 'Connection'


class AdminNote(models.Model):
    """PRD 7.2 — internal, admin-only notes; never exposed to the user discussed (PRD 8.2).

    entity_id is a CharField because platform entities (CustomUser, Application)
    use integer PKs while the PRD assumed UUIDs — a string holds either.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity_type = models.CharField(max_length=20, choices=EntityType.choices, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    author_admin = models.ForeignKey(AdminUser, on_delete=models.CASCADE, related_name='notes')
    note_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Note on {self.entity_type} {self.entity_id} by {self.author_admin.full_name}"


class AdminActionLog(models.Model):
    """PRD 7.3 — every admin action stays traceable (PRD 8.3)."""

    class ActionType(models.TextChoices):
        SUSPEND = 'suspend', 'Suspend'
        REINSTATE = 'reinstate', 'Reinstate'
        EDIT_PROFILE = 'edit_profile', 'Edit Profile'
        UPDATE_CONNECTION_STATUS = 'update_connection_status', 'Update Connection Status'
        SEND_MESSAGE = 'send_message', 'Send Message'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin = models.ForeignKey(AdminUser, on_delete=models.CASCADE, related_name='actions')
    action_type = models.CharField(max_length=30, choices=ActionType.choices, db_index=True)
    target_entity_type = models.CharField(max_length=20, choices=EntityType.choices)
    target_entity_id = models.CharField(max_length=64, db_index=True)
    reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action_type} on {self.target_entity_type} {self.target_entity_id}"


class BroadcastMessage(models.Model):
    """PRD 7.4 + 6.6 — platform-wide / segment messaging, with a log of past sends."""

    class Audience(models.TextChoices):
        ALL_PATHFINDERS = 'all_pathfinders', 'All Pathfinders'
        ALL_ENABLERS = 'all_enablers', 'All Enablers'
        ALL_USERS = 'all_users', 'All Users'
        CUSTOM_SEGMENT = 'custom_segment', 'Custom Segment'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sent_by_admin = models.ForeignKey(AdminUser, on_delete=models.CASCADE, related_name='broadcasts')
    audience = models.CharField(max_length=20, choices=Audience.choices)
    segment_filter = models.JSONField(null=True, blank=True)
    subject = models.CharField(max_length=200)
    message_body = models.TextField()
    recipient_count = models.IntegerField(default=0)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"[{self.audience}] {self.subject}"
