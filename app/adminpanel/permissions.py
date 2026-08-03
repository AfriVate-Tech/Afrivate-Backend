from rest_framework.permissions import BasePermission

from .models import AdminUser


class IsAdminPanelUser(BasePermission):
    """Only an authenticated, active AdminUser may reach admin routes (PRD 8.1).

    An isinstance check — a CustomUser (Pathfinder/Enabler) authenticated by any
    other means is rejected regardless of its flags.
    """

    message = 'Admin authentication required.'

    def has_permission(self, request, view):
        return isinstance(request.user, AdminUser) and request.user.is_active
