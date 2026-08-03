from django.urls import path

from . import views_actions, views_analytics, views_auth, views_broadcasts, views_connections, views_directory

urlpatterns = [
    # Sprint 1 — admin auth (PRD 11.1)
    path('auth/login/', views_auth.AdminLoginView.as_view(), name='admin-login'),
    path('auth/refresh/', views_auth.AdminTokenRefreshView.as_view(), name='admin-refresh'),
    path('auth/me/', views_auth.AdminMeView.as_view(), name='admin-me'),

    # Sprint 2 — directory & profiles (PRD 6.1–6.2)
    path('users/', views_directory.UserDirectoryView.as_view(), name='admin-users'),
    path('users/<int:user_id>/', views_directory.UserDetailView.as_view(), name='admin-user-detail'),
    path('notes/', views_directory.AdminNotesView.as_view(), name='admin-notes'),

    # Sprint 3 — account actions (PRD 6.3)
    path('users/<int:user_id>/suspend/', views_actions.SuspendUserView.as_view(), name='admin-suspend'),
    path('users/<int:user_id>/reinstate/', views_actions.ReinstateUserView.as_view(), name='admin-reinstate'),
    path('users/<int:user_id>/edit/', views_actions.EditUserView.as_view(), name='admin-edit-user'),
    path('users/<int:user_id>/message/', views_actions.MessageUserView.as_view(), name='admin-message-user'),
    path('messages/segment/', views_actions.MessageSegmentView.as_view(), name='admin-message-segment'),
    path('actions/', views_actions.ActionLogView.as_view(), name='admin-action-log'),

    # Sprint 4 — connection oversight (PRD 6.4)
    path('connections/', views_connections.ConnectionListView.as_view(), name='admin-connections'),
    path('connections/<int:connection_id>/', views_connections.ConnectionDetailView.as_view(), name='admin-connection-detail'),

    # Sprint 5 — analytics & broadcasts (PRD 6.5–6.6)
    path('analytics/overview/', views_analytics.AnalyticsOverviewView.as_view(), name='admin-analytics'),
    path('analytics/export/', views_analytics.AnalyticsExportView.as_view(), name='admin-analytics-export'),
    path('broadcasts/', views_broadcasts.BroadcastView.as_view(), name='admin-broadcasts'),
]
