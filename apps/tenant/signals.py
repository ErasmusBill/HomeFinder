from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.core.cache import cache
from apps.home_finder.models import Property
from apps.tenant.models import SavedProperty, PropertyView, PropertyAlert, ViewingRequest
from apps.tenant.selectors import get_saved_properties_cache_key, get_property_views_cache_key, get_property_alerts_cache_key, get_viewing_requests_cache_key

@receiver([post_save, post_delete], sender=SavedProperty)
def invalidate_saved_property_cache(sender, instance, **kwargs):
    cache.delete(get_saved_properties_cache_key(instance.tenant_id))

@receiver([post_save, post_delete], sender=PropertyView)
def invalidate_property_view_cache(sender, instance, **kwargs):
    cache.delete(get_property_views_cache_key(instance.tenant_id))

@receiver([post_save, post_delete], sender=PropertyAlert)
def invalidate_property_alert_cache(sender, instance, **kwargs):
    cache.delete(get_property_alerts_cache_key(instance.tenant_id))

@receiver([post_save, post_delete], sender=ViewingRequest)
def invalidate_viewing_request_cache(sender, instance, **kwargs):
    cache.delete(get_viewing_requests_cache_key(instance.tenant_id))

@receiver([post_save, post_delete], sender=Property)
def invalidate_property_related_caches(sender, instance, **kwargs):
    for tenant_id in SavedProperty.objects.filter(property=instance).values_list("tenant_id", flat=True):
        cache.delete(get_saved_properties_cache_key(tenant_id))
    for tenant_id in PropertyView.objects.filter(property=instance).values_list("tenant_id", flat=True):
        cache.delete(get_property_views_cache_key(tenant_id))
    for tenant_id in ViewingRequest.objects.filter(property=instance).values_list("tenant_id", flat=True):
        cache.delete(get_viewing_requests_cache_key(tenant_id))