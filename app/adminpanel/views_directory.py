from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from applications.models import Application
from opportunities.models import Opportunity
from user_database.models import CustomUser

from .authentication import AdminJWTAuthentication
from .models import AdminNote, EntityType
from .permissions import IsAdminPanelUser
from .serializers import AdminNoteSerializer, ConnectionSerializer, DirectoryRowSerializer
from .utils import account_status, csv_response, display_name, filter_users


class AdminAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminPanelUser]


class DirectoryPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


class UserDirectoryView(AdminAPIView):
    """PRD 6.1 — unified, searchable, filterable directory of both user types.
    `?export=csv` streams the current filtered view (PRD 6.5.2)."""

    def get(self, request):
        qs = filter_users(request.query_params)

        if request.query_params.get('export') == 'csv':
            rows = [
                (
                    u.id, display_name(u), u.email, u.role,
                    u.date_joined.date(), u.last_login.date() if u.last_login else '',
                    account_status(u),
                    getattr(getattr(u, 'profile', None), 'state', '') or '',
                )
                for u in qs
            ]
            return csv_response(
                'afrivate_users.csv',
                ['ID', 'Name', 'Email', 'Type', 'Signup Date', 'Last Active', 'Status', 'State'],
                rows,
            )

        paginator = DirectoryPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(DirectoryRowSerializer(page, many=True).data)


def _user_connections(user):
    """Every engagement this user has been part of (PRD 6.2.3)."""
    if user.role == 'enabler':
        qs = Application.objects.filter(opportunity__created_by=user)
    else:
        qs = user.applications.all()
    return qs.select_related('user__profile', 'opportunity__created_by__profile')


def _activity_timeline(user):
    """PRD 6.2.1 — assembled from stored timestamps (signup, last login,
    applications, reviews). Historical per-login events are not stored by the
    platform, so only the most recent login can appear."""
    events = [{'at': user.date_joined, 'event': 'Signed up'}]
    if user.last_login:
        events.append({'at': user.last_login, 'event': 'Last login'})

    if user.role == 'enabler':
        for opp in Opportunity.objects.filter(created_by=user):
            events.append({'at': opp.posted_at, 'event': f'Posted opportunity: {opp.title}'})
        for app in _user_connections(user):
            events.append({
                'at': app.applied_at,
                'event': f'Received application from {display_name(app.user)} for {app.opportunity.title}',
            })
    else:
        for app in _user_connections(user):
            events.append({'at': app.applied_at, 'event': f'Applied to {app.opportunity.title}'})
            if app.reviewed_at:
                events.append({
                    'at': app.reviewed_at,
                    'event': f'Application to {app.opportunity.title} marked {app.status}',
                })

    return sorted(events, key=lambda e: e['at'], reverse=True)


class UserDetailView(AdminAPIView):
    """PRD 6.2 — full detail view for a Pathfinder or Enabler."""

    def get(self, request, user_id):
        user = get_object_or_404(
            CustomUser.objects.select_related(
                'profile', 'profile__enabler_extra', 'profile__pathfinder_extra'
            ),
            id=user_id, is_superuser=False,
        )
        profile = getattr(user, 'profile', None)

        data = {
            'id': user.id,
            'name': display_name(user),
            'username': user.username,
            'email': user.email,
            'type': user.role,
            'status': account_status(user),
            'is_suspended': user.is_suspended,
            'is_email_verified': user.is_email_verified,
            'auth_provider': user.auth_provider,
            'signup_date': user.date_joined,
            'last_active': user.last_login,
            'profile': None,
            'activity_timeline': _activity_timeline(user),
        }

        if profile:
            data['profile'] = {
                'bio': profile.bio,
                'contact_email': profile.contact_email,
                'phone_number': profile.phone_number,
                'address': profile.address,
                'state': profile.state,
                'country': profile.country,
                'website': profile.website,
                'profile_pic': profile.profile_pic.url if profile.profile_pic else None,
            }
            pathfinder_extra = getattr(profile, 'pathfinder_extra', None)
            if pathfinder_extra:
                data['pathfinder'] = {
                    'first_name': pathfinder_extra.first_name,
                    'last_name': pathfinder_extra.last_name,
                    'title': pathfinder_extra.title,
                    'about': pathfinder_extra.about,
                    'languages': pathfinder_extra.languages,
                    'skills': list(pathfinder_extra.pathfinder_skills.values_list('name', flat=True)),
                    'education': list(pathfinder_extra.pathfinder_education.values_list('name', flat=True)),
                    'certifications': list(
                        pathfinder_extra.pathfinder_certifications.values_list('name', flat=True)
                    ),
                }
            enabler_extra = getattr(profile, 'enabler_extra', None)
            if enabler_extra:
                data['enabler'] = {
                    'organization_name': enabler_extra.name,
                    'employees': enabler_extra.employees,
                    'contact_role': enabler_extra.role,
                    'opportunities_posted': Opportunity.objects.filter(created_by=user).count(),
                    'volunteers_connected': Application.objects.filter(
                        opportunity__created_by=user
                    ).exclude(status__in=['pending', 'rejected']).count(),
                }

        connections = _user_connections(user)
        data['connections'] = ConnectionSerializer(connections, many=True).data
        return Response(data)


class AdminNotesView(AdminAPIView):
    """PRD 6.2.4 — timestamped, attributed, admin-only notes (never user-visible, PRD 8.2)."""

    def get(self, request):
        entity_type = request.query_params.get('entity_type')
        entity_id = request.query_params.get('entity_id')
        if entity_type not in EntityType.values or not entity_id:
            return Response(
                {'detail': 'entity_type and entity_id are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notes = AdminNote.objects.filter(
            entity_type=entity_type, entity_id=str(entity_id)
        ).select_related('author_admin')
        return Response(AdminNoteSerializer(notes, many=True).data)

    def post(self, request):
        serializer = AdminNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(author_admin=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
