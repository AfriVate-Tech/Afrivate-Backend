"""
URL configuration for Afrivate project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include

from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

import Authentication.views

schema_view = get_schema_view(
    openapi.Info(
        title="Afrivate API",
        default_version='v1',
        description="Afrivate API powers Afrivate's mobile and web platforms, managing user data, orders, carts, and more. Built for security and scalability, it includes features like JWT authentication, product management, order processing, payment integration, and real-time notifications. it ensures a seamless shopping experience",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API Documentation
    path('api/v1/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('docs/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    path('api-auth/', include('rest_framework.urls')),  # Django REST framework login/logout views

    # app's urls 
    path("", Authentication.views.index,),  # Added to serve index view
    path('api/auth/', include('Authentication.urls')),
    path("api/waitlist/", include("waitlist.urls")),
    path("api/profile/", include("profiles.urls")),
    path("api/bookmark/", include("bookmark.urls")),
    path("api/notify/", include("notifications.urls")),
    path("api/opportunities/", include("opportunities.urls")),
    path("api/applications/", include("applications.urls")),
]

# Media files are served by Cloudinary (see STORAGES in settings.py),
# so no local /media/ route is needed, even in DEBUG.