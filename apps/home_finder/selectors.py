from django.conf import settings
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from apps.home_finder.models import Property

CACHE_TTL = getattr(settings, "CACHE_TTL", 300)

def _property_cache_key(prefix, *args):
    return ":".join(["properties", prefix, *[str(arg) for arg in args if arg is not None]])

def _property_queryset():
    return Property.objects.filter(
        publication_status=Property.PublicationStatus.PUBLISHED,
        verification_status=Property.VerificationStatus.VERIFIED,
        is_available=True,
    ).select_related(
        "region",
        "district",
        "town",
        "area",
        "landlord",
    ).prefetch_related(
        "amenities",
        "media",
        "landlord__subscriptions",
    )

def _attach_landlord_subscription_flag(properties):
    """Set a runtime-only attribute landlord_has_active_subscription on each property.landlord.
    This avoids extra DB queries in templates.
    """
    now = timezone.now()
    for prop in properties:
        try:
            landlord = prop.landlord
            # related name 'subscriptions' exists on LandlordSubscription
            has_active = any(
                s.is_active and (s.end_date is None or s.end_date > now)
                for s in getattr(landlord, 'subscriptions').all()
            )
            setattr(prop, 'landlord_has_active_subscription', has_active)
        except Exception:
            setattr(prop, 'landlord_has_active_subscription', False)

def get_published_properties(limit=None):
    cache_key = _property_cache_key("published", limit)
    properties = cache.get(cache_key)
    if properties is None:
        qs = _property_queryset().order_by("-created_at")
        if limit:
            qs = qs[:limit]
        properties = list(qs)
        _attach_landlord_subscription_flag(properties)
        cache.set(cache_key, properties, CACHE_TTL)
    return properties

def get_featured_properties(limit=8):
    cache_key = _property_cache_key("featured", limit)
    properties = cache.get(cache_key)
    if properties is None:
        qs = _property_queryset().filter(is_featured=True).order_by("-created_at")
        if limit:
            qs = qs[:limit]
        properties = list(qs)
        _attach_landlord_subscription_flag(properties)
        cache.set(cache_key, properties, CACHE_TTL)
    return properties
@@
 def get_recent_properties(limit=12):
     cache_key = _property_cache_key("recent", limit)
     properties = cache.get(cache_key)
     if properties is None:
-        properties = list(_property_queryset().order_by("-created_at")[:limit])
+        qs = _property_queryset().order_by("-created_at")
+        if limit:
+            qs = qs[:limit]
+        properties = list(qs)
+        _attach_landlord_subscription_flag(properties)
         cache.set(cache_key, properties, CACHE_TTL)
     return properties
