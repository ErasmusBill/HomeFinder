from django.core.cache import cache
from apps.tenant.models import PropertyAlert, PropertyView, SavedProperty, ViewingRequest


def get_saved_properties_cache_key(tenant_id):
    return f"tenant_saved_properties_{tenant_id}"


def get_property_views_cache_key(tenant_id):
    return f"tenant_property_views_{tenant_id}"


def get_property_alerts_cache_key(tenant_id):
    return f"tenant_property_alerts_{tenant_id}"


def get_viewing_requests_cache_key(tenant_id):
    return f"tenant_viewing_requests_{tenant_id}"



def get_tenant_saved_properties(tenant):
    """Retrieves and caches the list of saved properties for a given tenant."""
    cache_key = get_saved_properties_cache_key(tenant.pk)
    properties = cache.get(cache_key)

    if properties is None:
        properties = list(
            SavedProperty.objects.filter(tenant=tenant)
            .select_related("property", "property__region", "property__district")
        )
        cache.set(cache_key, properties, timeout=3600)  # Cache for 1 hour

    return properties


def get_tenant_property_views(tenant):
    """Retrieves and caches the property viewing history for a given tenant."""
    cache_key = get_property_views_cache_key(tenant.pk)
    views = cache.get(cache_key)

    if views is None:
        views = list(
            PropertyView.objects.filter(tenant=tenant)
            .select_related("property")
            .order_by("-viewed_at")
        )
        cache.set(cache_key, views, timeout=1800)  # Cache for 30 minutes

    return views


def get_tenant_property_alerts(tenant):
    """Retrieves and caches active property search alerts for a given tenant."""
    cache_key = get_property_alerts_cache_key(tenant.pk)
    alerts = cache.get(cache_key)

    if alerts is None:
        alerts = list(
            PropertyAlert.objects.filter(tenant=tenant, is_active=True)
            .select_related("region", "district", "area")
        )
        cache.set(cache_key, alerts, timeout=3600)  # Cache for 1 hour

    return alerts


def get_tenant_viewing_requests(tenant):
    """Retrieves and caches scheduled viewing requests for a given tenant."""
    cache_key = get_viewing_requests_cache_key(tenant.pk)
    requests = cache.get(cache_key)

    if requests is None:
        requests = list(
            ViewingRequest.objects.filter(tenant=tenant)
            .select_related("property")
            .order_by("-preferred_date", "-preferred_time")
        )
        cache.set(cache_key, requests, timeout=900)  # Cache for 15 minutes

    return requests
