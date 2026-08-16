from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import Q

from apps.notifications.models import Notification
from apps.tenant.models import PropertyAlert, PropertyView, SavedProperty, ViewingRequest

SAVED_PROPERTIES_CACHE_TIMEOUT = 60 * 60
PROPERTY_VIEWS_CACHE_TIMEOUT = 60 * 30
PROPERTY_ALERTS_CACHE_TIMEOUT = 60 * 60
VIEWING_REQUESTS_CACHE_TIMEOUT = 60 * 15

def get_saved_properties_cache_key(tenant_id):
    return f"tenant:saved_properties:{tenant_id}"

def get_property_views_cache_key(tenant_id):
    return f"tenant:property_views:{tenant_id}"

def get_property_alerts_cache_key(tenant_id):
    return f"tenant:property_alerts:{tenant_id}"

def get_viewing_requests_cache_key(tenant_id):
    return f"tenant:viewing_requests:{tenant_id}"

def get_tenant_saved_properties(tenant):
    cache_key = get_saved_properties_cache_key(tenant.pk)
    saved_properties = cache.get(cache_key)
    if saved_properties is None:
        saved_properties = list(SavedProperty.objects.filter(tenant=tenant).select_related("property", "property__region", "property__district", "property__area").order_by("-created_at"))
        cache.set(cache_key, saved_properties, timeout=SAVED_PROPERTIES_CACHE_TIMEOUT)
    return saved_properties

def get_tenant_saved_property_count(tenant):
    return SavedProperty.objects.filter(tenant=tenant).count()

def get_tenant_saved_property(tenant, property_id):
    return SavedProperty.objects.filter(tenant=tenant, property_id=property_id).select_related("property", "property__region", "property__district", "property__area").first()

def get_tenant_property_views(tenant):
    cache_key = get_property_views_cache_key(tenant.pk)
    property_views = cache.get(cache_key)
    if property_views is None:
        property_views = list(PropertyView.objects.filter(tenant=tenant).select_related("property", "property__region", "property__district", "property__area").order_by("-viewed_at"))
        cache.set(cache_key, property_views, timeout=PROPERTY_VIEWS_CACHE_TIMEOUT)
    return property_views

def get_tenant_property_view_count(tenant):
    return PropertyView.objects.filter(tenant=tenant).count()

def get_tenant_recent_property_views(tenant, limit=6):
    property_views = get_tenant_property_views(tenant)
    return property_views[:limit]

def get_tenant_property_view(tenant, property_id):
    return PropertyView.objects.filter(tenant=tenant, property_id=property_id).select_related("property", "property__region", "property__district", "property__area").first()

def get_tenant_property_alerts(tenant):
    cache_key = get_property_alerts_cache_key(tenant.pk)
    alerts = cache.get(cache_key)
    if alerts is None:
        alerts = list(PropertyAlert.objects.filter(tenant=tenant, is_active=True).select_related("region", "district", "area").order_by("-created_at"))
        cache.set(cache_key, alerts, timeout=PROPERTY_ALERTS_CACHE_TIMEOUT)
    return alerts

def get_tenant_all_property_alerts(tenant):
    return list(PropertyAlert.objects.filter(tenant=tenant).select_related("region", "district", "area").order_by("-created_at"))

def get_tenant_property_alert_count(tenant):
    return PropertyAlert.objects.filter(tenant=tenant, is_active=True).count()

def get_tenant_property_alert(tenant, alert_id):
    return PropertyAlert.objects.filter(tenant=tenant, pk=alert_id).select_related("region", "district", "area").first()

def get_tenant_viewing_requests(tenant):
    cache_key = get_viewing_requests_cache_key(tenant.pk)
    viewing_requests = cache.get(cache_key)
    if viewing_requests is None:
        viewing_requests = list(ViewingRequest.objects.filter(tenant=tenant).select_related("property", "property__region", "property__district", "property__area").order_by("-preferred_date", "-preferred_time", "-created_at"))
        cache.set(cache_key, viewing_requests, timeout=VIEWING_REQUESTS_CACHE_TIMEOUT)
    return viewing_requests

def get_tenant_viewing_request_count(tenant):
    return ViewingRequest.objects.filter(tenant=tenant).count()

def get_tenant_pending_viewing_request_count(tenant):
    return ViewingRequest.objects.filter(tenant=tenant, status=ViewingRequest.Status.PENDING).count()

def get_tenant_upcoming_viewing_requests(tenant, limit=5):
    viewing_requests = ViewingRequest.objects.filter(tenant=tenant, status__in=[ViewingRequest.Status.PENDING, ViewingRequest.Status.CONFIRMED]).select_related("property", "property__region", "property__district", "property__area").order_by("preferred_date", "preferred_time")
    return list(viewing_requests[:limit])

def get_tenant_viewing_request(tenant, request_id):
    return ViewingRequest.objects.filter(tenant=tenant, pk=request_id).select_related("property", "property__region", "property__district", "property__area").first()

def get_tenant_dashboard_summary(tenant):
    return {"saved_count": get_tenant_saved_property_count(tenant), "views_count": get_tenant_property_view_count(tenant), "alerts_count": get_tenant_property_alert_count(tenant), "requests_count": get_tenant_viewing_request_count(tenant), "pending_requests_count": get_tenant_pending_viewing_request_count(tenant)}

def get_tenant_dashboard_saved_properties(tenant, limit=4):
    return get_tenant_saved_properties(tenant)[:limit]

def get_tenant_dashboard_property_views(tenant, limit=4):
    return get_tenant_recent_property_views(tenant, limit=limit)

def get_tenant_dashboard_property_alerts(tenant, limit=3):
    return get_tenant_property_alerts(tenant)[:limit]

def get_tenant_dashboard_viewing_requests(tenant, limit=3):
    return get_tenant_upcoming_viewing_requests(tenant, limit=limit)


def get_all_tenant_related_notifications(tenant_instance):
    """
    Fetches all notifications where:
    1. The recipient is the tenant's user account.
    2. The sender/creator is the tenant's user account.
    3. The notification target (GFK) points directly to the tenant model.
    """
    tenant_type = ContentType.objects.get_for_model(tenant_instance)

    # Assuming tenant_instance has a user relationship (e.g., tenant_instance.user)
    # or tenant_instance is itself a User instance.
    user = getattr(tenant_instance, 'user', tenant_instance)

    return Notification.objects.filter(
        Q(user=user) |
        Q(created_by=user) |
        Q(content_type=tenant_type, object_id=str(tenant_instance.pk))
    ).select_related('user', 'created_by').distinct()