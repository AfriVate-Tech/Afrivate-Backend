from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from applications.models import Application
from opportunities.models import Opportunity
from user_database.models import CustomUser

from .utils import INACTIVITY_DAYS, csv_response
from .views_directory import AdminAPIView


def _window(request):
    """PRD 6.5.1 — every chart/table takes a date-range filter.
    Either ?days=7|30|90 or ?from=YYYY-MM-DD&to=YYYY-MM-DD."""
    now = timezone.now()
    date_from = request.query_params.get('from')
    date_to = request.query_params.get('to')
    if date_from:
        return date_from, date_to or now.date().isoformat()
    days = int(request.query_params.get('days') or 30)
    return (now - timedelta(days=days)).date().isoformat(), now.date().isoformat()


def _analytics(date_from, date_to):
    users = CustomUser.objects.filter(is_superuser=False)
    in_range_users = users.filter(date_joined__date__gte=date_from, date_joined__date__lte=date_to)
    in_range_apps = Application.objects.filter(
        applied_at__date__gte=date_from, applied_at__date__lte=date_to
    )

    # Growth — new signups by type, plus a daily series for charting
    growth_series = list(
        in_range_users.values('date_joined__date')
        .annotate(
            pathfinders=Count('id', filter=Q(role='pathfinder')),
            enablers=Count('id', filter=Q(role='enabler')),
        )
        .order_by('date_joined__date')
    )

    # Activity — active vs dormant by type (login within the inactivity window)
    cutoff = timezone.now() - timedelta(days=INACTIVITY_DAYS)
    recent = Q(last_login__gte=cutoff) | Q(last_login__isnull=True, date_joined__gte=cutoff)
    activity = {
        role: {
            'active': users.filter(role=role, is_suspended=False).filter(recent).count(),
            'dormant': users.filter(role=role, is_suspended=False).exclude(recent).count(),
            'suspended': users.filter(role=role, is_suspended=True).count(),
        }
        for role in ('pathfinder', 'enabler')
    }

    # Engagement funnel — signups -> applications -> connections made -> completed.
    # ("Opportunities viewed" is not tracked by the platform yet; the funnel
    # starts at applications until view-tracking exists.)
    funnel = {
        'signups': in_range_users.count(),
        'applications_made': in_range_apps.count(),
        'connections_made': in_range_apps.filter(status__in=['accepted', 'active', 'completed']).count(),
        'connections_completed': in_range_apps.filter(status='completed').count(),
    }

    # Geographic breakdown — users and connections by state
    geography = list(
        users.exclude(Q(profile__state__isnull=True) | Q(profile__state=''))
        .values('profile__state')
        .annotate(
            users=Count('id'),
            pathfinders=Count('id', filter=Q(role='pathfinder')),
            enablers=Count('id', filter=Q(role='enabler')),
        )
        .order_by('-users')[:25]
    )

    # Organization activity — opportunities posted per enabler, most active first
    org_activity = list(
        Opportunity.objects.values(
            'created_by__id', 'created_by__username', 'created_by__email',
            'created_by__profile__enabler_extra__name',
        )
        .annotate(
            opportunities_posted=Count('id', distinct=True),
            applications_received=Count('applicants', distinct=True),
        )
        .order_by('-opportunities_posted')[:25]
    )

    return {
        'date_from': date_from,
        'date_to': date_to,
        'totals': {
            'pathfinders': users.filter(role='pathfinder').count(),
            'enablers': users.filter(role='enabler').count(),
            'opportunities': Opportunity.objects.count(),
            'connections': Application.objects.count(),
        },
        'growth': {
            'new_pathfinders': in_range_users.filter(role='pathfinder').count(),
            'new_enablers': in_range_users.filter(role='enabler').count(),
            'series': [
                {'date': row['date_joined__date'], 'pathfinders': row['pathfinders'],
                 'enablers': row['enablers']}
                for row in growth_series
            ],
        },
        'activity': activity,
        'funnel': funnel,
        'geography': [
            {'state': row['profile__state'], 'users': row['users'],
             'pathfinders': row['pathfinders'], 'enablers': row['enablers']}
            for row in geography
        ],
        'organization_activity': [
            {
                'enabler_id': row['created_by__id'],
                'organization': row['created_by__profile__enabler_extra__name']
                or row['created_by__username'],
                'email': row['created_by__email'],
                'opportunities_posted': row['opportunities_posted'],
                'applications_received': row['applications_received'],
            }
            for row in org_activity
        ],
    }


class AnalyticsOverviewView(AdminAPIView):
    """PRD 6.5 — the core metrics dashboard."""

    def get(self, request):
        date_from, date_to = _window(request)
        return Response(_analytics(date_from, date_to))


class AnalyticsExportView(AdminAPIView):
    """PRD 6.5.2 — CSV export for each report table: ?table=growth|geography|organizations|funnel."""

    def get(self, request):
        date_from, date_to = _window(request)
        data = _analytics(date_from, date_to)
        table = request.query_params.get('table')

        if table == 'growth':
            return csv_response(
                'afrivate_growth.csv', ['Date', 'New Pathfinders', 'New Enablers'],
                [(r['date'], r['pathfinders'], r['enablers']) for r in data['growth']['series']],
            )
        if table == 'geography':
            return csv_response(
                'afrivate_geography.csv', ['State', 'Users', 'Pathfinders', 'Enablers'],
                [(r['state'], r['users'], r['pathfinders'], r['enablers'])
                 for r in data['geography']],
            )
        if table == 'organizations':
            return csv_response(
                'afrivate_organizations.csv',
                ['Organization', 'Email', 'Opportunities Posted', 'Applications Received'],
                [(r['organization'], r['email'], r['opportunities_posted'],
                  r['applications_received']) for r in data['organization_activity']],
            )
        if table == 'funnel':
            return csv_response(
                'afrivate_funnel.csv', ['Stage', 'Count'],
                list(data['funnel'].items()),
            )
        return Response(
            {'detail': 'table must be one of growth, geography, organizations, funnel.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
