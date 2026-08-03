from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from applications.models import Application

from .models import AdminActionLog
from .serializers import ConnectionSerializer
from .utils import csv_response, display_name, log_action
from .views_directory import AdminAPIView, DirectoryPagination


def _filter_connections(params):
    """PRD 6.4.1 — filterable by status, date range, organization/volunteer."""
    qs = Application.objects.select_related(
        'user__profile__pathfinder_extra',
        'opportunity__created_by__profile__enabler_extra',
    )

    conn_status = params.get('status')
    if conn_status:
        qs = qs.filter(status=conn_status)

    if params.get('from'):
        qs = qs.filter(applied_at__date__gte=params['from'])
    if params.get('to'):
        qs = qs.filter(applied_at__date__lte=params['to'])

    q = (params.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
            | Q(user__profile__pathfinder_extra__first_name__icontains=q)
            | Q(user__profile__pathfinder_extra__last_name__icontains=q)
            | Q(opportunity__title__icontains=q)
            | Q(opportunity__created_by__profile__enabler_extra__name__icontains=q)
            | Q(opportunity__created_by__email__icontains=q)
        )
    return qs.distinct()


class ConnectionListView(AdminAPIView):
    """PRD 6.4.1 — all connections, independent of profile views."""

    def get(self, request):
        qs = _filter_connections(request.query_params)

        if request.query_params.get('export') == 'csv':
            rows = [
                (
                    c.id, display_name(c.user), c.user.email,
                    display_name(c.opportunity.created_by), c.opportunity.title,
                    c.status, c.applied_at.date(),
                    c.reviewed_at.date() if c.reviewed_at else '',
                )
                for c in qs
            ]
            return csv_response(
                'afrivate_connections.csv',
                ['ID', 'Pathfinder', 'Pathfinder Email', 'Enabler', 'Opportunity',
                 'Status', 'Applied', 'Reviewed'],
                rows,
            )

        paginator = DirectoryPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ConnectionSerializer(page, many=True).data)


class ConnectionDetailView(AdminAPIView):
    """PRD 6.4.2 (detail) and 6.4.3 (direct status correction, logged)."""

    def get(self, request, connection_id):
        conn = get_object_or_404(_filter_connections({}), id=connection_id)
        return Response(ConnectionSerializer(conn).data)

    def patch(self, request, connection_id):
        conn = get_object_or_404(Application, id=connection_id)
        new_status = request.data.get('status')
        reason = (request.data.get('reason') or '').strip()

        valid = [choice[0] for choice in Application.STATUS_CHOICES]
        if new_status not in valid:
            return Response(
                {'detail': f"status must be one of {valid}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not reason:
            return Response(
                {'detail': 'A reason is required when correcting a connection status.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = conn.status
        conn.status = new_status
        conn.save(update_fields=['status'])

        log_action(
            request.user, AdminActionLog.ActionType.UPDATE_CONNECTION_STATUS,
            'connection', conn.id,
            reason=f"'{old_status}' -> '{new_status}': {reason}",
        )
        return Response(ConnectionSerializer(conn).data)
