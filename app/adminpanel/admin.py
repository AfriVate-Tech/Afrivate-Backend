from django.contrib import admin

from .models import AdminActionLog, AdminNote, AdminUser, BroadcastMessage


@admin.register(AdminUser)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'is_active', 'last_login', 'created_at')
    search_fields = ('full_name', 'email')
    readonly_fields = ('password',)


@admin.register(AdminNote)
class AdminNoteAdmin(admin.ModelAdmin):
    list_display = ('entity_type', 'entity_id', 'author_admin', 'created_at')
    list_filter = ('entity_type',)


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    list_display = ('action_type', 'target_entity_type', 'target_entity_id', 'admin', 'created_at')
    list_filter = ('action_type', 'target_entity_type')
    readonly_fields = [f.name for f in AdminActionLog._meta.fields]


@admin.register(BroadcastMessage)
class BroadcastMessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'audience', 'recipient_count', 'sent_by_admin', 'sent_at')
    list_filter = ('audience',)
