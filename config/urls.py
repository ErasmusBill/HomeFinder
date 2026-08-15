"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path,include

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.home_finder.urls')),
    path('locations/', include('apps.locations.urls')),
    path('landloards/', include('apps.landloards.urls')),
    path('account/', include('apps.account.urls')),
    path('accounts/', include('allauth.urls')),
    path('subscription/', include('apps.Subscription.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('tenants/', include('apps.tenant.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)