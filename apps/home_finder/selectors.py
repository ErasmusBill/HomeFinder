from django.conf import settings
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.db.models import Q
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
    ).prefetch_related(
        "amenities",
        "media",
    )

def get_published_properties():
    cache_key = _property_cache_key("published")
    properties = cache.get(cache_key)
    if properties is None:
        properties = list(_property_queryset().order_by("-created_at"))
        cache.set(cache_key, properties, CACHE_TTL)
    return properties

def get_property_by_slug(slug):
    cache_key = _property_cache_key("slug", slug)
    property_obj = cache.get(cache_key)
    if property_obj is None:
        property_obj = get_object_or_404(_property_queryset(), slug=slug)
        cache.set(cache_key, property_obj, CACHE_TTL)
    return property_obj

# def get_featured_properties(limit=8):
#     cache_key = _property_cache_key("featured", limit)
#     properties = cache.get(cache_key)
#     if properties is None:
#         properties = list(_property_queryset().filter(is_featured=True).order_by("-created_at")[:limit])
#         cache.set(cache_key, properties, CACHE_TTL)
#     return properties

def get_recent_properties(limit=12):
    cache_key = _property_cache_key("recent", limit)
    properties = cache.get(cache_key)
    if properties is None:
        properties = list(_property_queryset().order_by("-created_at")[:limit])
        cache.set(cache_key, properties, CACHE_TTL)
    return properties

def get_properties_by_region(region):
    cache_key = _property_cache_key("region", region.pk)
    properties = cache.get(cache_key)
    if properties is None:
        properties = list(_property_queryset().filter(region=region).order_by("-created_at"))
        cache.set(cache_key, properties, CACHE_TTL)
    return properties

def get_properties_by_district(district):
    cache_key = _property_cache_key("district", district.pk)
    properties = cache.get(cache_key)
    if properties is None:
        properties = list(_property_queryset().filter(district=district).order_by("-created_at"))
        cache.set(cache_key, properties, CACHE_TTL)
    return properties

def get_properties_by_area(area):
    cache_key = _property_cache_key("area", area.pk)
    properties = cache.get(cache_key)
    if properties is None:
        properties = list(_property_queryset().filter(area=area).order_by("-created_at"))
        cache.set(cache_key, properties, CACHE_TTL)
    return properties

def get_properties_by_price(min_price=None, max_price=None):
    cache_key = _property_cache_key("price", min_price, max_price)
    properties = cache.get(cache_key)
    if properties is None:
        queryset = _property_queryset()
        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)
        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)
        properties = list(queryset.order_by("price"))
        cache.set(cache_key, properties, CACHE_TTL)
    return properties

def search_properties(query):
    cache_key = _property_cache_key("search", query.lower())
    properties = cache.get(cache_key)
    if properties is None:
        properties = list(_property_queryset().filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(region__name__icontains=query)
            | Q(district__name__icontains=query)
            | Q(town__name__icontains=query)
            | Q(area__name__icontains=query)
        ).distinct().order_by("-created_at"))
        cache.set(cache_key, properties, CACHE_TTL)
    return properties

def get_property(pk):
    cache_key = _property_cache_key("detail", pk)
    property_obj = cache.get(cache_key)
    if property_obj is None:
        property_obj = get_object_or_404(_property_queryset(), pk=pk)
        cache.set(cache_key, property_obj, CACHE_TTL)
    return property_obj

# The local invalidate_property_cache has been moved to apps.common.cache
from apps.common.cache import invalidate_property_cache


def get_admin_property_queryset():
    return Property.objects.all().select_related(
        "region",
        "district",
        "town",
        "area",
    ).prefetch_related(
        "amenities",
        "media",
    ).order_by("-created_at")

def get_admin_property(pk):
    return get_object_or_404(get_admin_property_queryset(), pk=pk)