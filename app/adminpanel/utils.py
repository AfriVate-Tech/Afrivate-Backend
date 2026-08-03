"""Shared helpers: audit logging (PRD 8.3), CSV export (PRD 6.5),
and the directory filter logic that segment messaging reuses (PRD 6.6.2)."""

import csv
from datetime import timedelta

from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone

from user_database.models import CustomUser

from .models import AdminActionLog

# A user with no login in this window counts as "inactive"/dormant (PRD 6.1.2, 6.5).
INACTIVITY_DAYS = 30


def log_action(admin, action_type, target_entity_type, target_entity_id, reason=None):
    return AdminActionLog.objects.create(
        admin=admin,
        action_type=action_type,
        target_entity_type=target_entity_type,
        target_entity_id=str(target_entity_id),
        reason=reason,
    )


def csv_response(filename, header, rows):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


def account_status(user):
    """active / inactive / suspended — suspension is stored, dormancy is derived."""
    if getattr(user, 'is_suspended', False):
        return 'suspended'
    cutoff = timezone.now() - timedelta(days=INACTIVITY_DAYS)
    reference = user.last_login or user.date_joined
    return 'active' if reference >= cutoff else 'inactive'


def filter_users(params):
    """PRD 6.1 filter panel, shared by the directory list, CSV export and
    segment messaging (6.3.3 / 6.6.2). `params` is a dict-like of query params:

    q           — matches name, email, phone number, organization name
    type        — pathfinder | enabler
    status      — active | inactive | suspended
    signup_from — YYYY-MM-DD
    signup_to   — YYYY-MM-DD
    state       — profile state/city text match
    """
    qs = CustomUser.objects.filter(is_superuser=False).select_related(
        'profile', 'profile__enabler_extra', 'profile__pathfinder_extra'
    )

    q = (params.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(profile__phone_number__icontains=q)
            | Q(profile__enabler_extra__name__icontains=q)
            | Q(profile__pathfinder_extra__first_name__icontains=q)
            | Q(profile__pathfinder_extra__last_name__icontains=q)
        )

    user_type = params.get('type')
    if user_type in ('pathfinder', 'enabler'):
        qs = qs.filter(role=user_type)

    status = params.get('status')
    cutoff = timezone.now() - timedelta(days=INACTIVITY_DAYS)
    if status == 'suspended':
        qs = qs.filter(is_suspended=True)
    elif status == 'active':
        qs = qs.filter(is_suspended=False).filter(
            Q(last_login__gte=cutoff) | Q(last_login__isnull=True, date_joined__gte=cutoff)
        )
    elif status == 'inactive':
        qs = qs.filter(is_suspended=False).filter(
            Q(last_login__lt=cutoff) | Q(last_login__isnull=True, date_joined__lt=cutoff)
        )

    if params.get('signup_from'):
        qs = qs.filter(date_joined__date__gte=params['signup_from'])
    if params.get('signup_to'):
        qs = qs.filter(date_joined__date__lte=params['signup_to'])

    state = (params.get('state') or '').strip()
    if state:
        qs = qs.filter(
            Q(profile__state__icontains=state) | Q(profile__address__icontains=state)
        )

    sort = params.get('sort') or '-date_joined'
    sort_map = {
        'name': 'username', '-name': '-username',
        'type': 'role', '-type': '-role',
        'signup': 'date_joined', '-signup': '-date_joined',
        'last_active': 'last_login', '-last_active': '-last_login',
        'date_joined': 'date_joined', '-date_joined': '-date_joined',
    }
    return qs.order_by(sort_map.get(sort, '-date_joined')).distinct()


def display_name(user):
    """Human name for lists: org name for enablers, full name for pathfinders."""
    profile = getattr(user, 'profile', None)
    if profile is not None:
        enabler_extra = getattr(profile, 'enabler_extra', None)
        if enabler_extra is not None and enabler_extra.name:
            return enabler_extra.name
        pathfinder_extra = getattr(profile, 'pathfinder_extra', None)
        if pathfinder_extra is not None:
            full = f"{pathfinder_extra.first_name} {pathfinder_extra.last_name}".strip()
            if full:
                return full
    return user.username
