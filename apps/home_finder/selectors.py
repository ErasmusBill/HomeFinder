from django.conf import settings
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.db.models import Q
from apps.home_finder.models import Property, LandlordDocument

CACHE_TTL = getattr(settings, "CACHE_TTL", 300)

def _property_cache_key(prefix, *args):
    return ":".join(["properties", prefix, *[str(arg) for arg in args if arg is not None]])

def _property_queryset():
    verified_docs_q = (
        Q(
            landlord_documents__verification_status=LandlordDocument.VerificationStatus.VERIFIED
        )
        | Q(
            landlord__documents__document_type=LandlordDocument.DocumentType.NATIONAL_ID,
            landlord__documents__verification_status=LandlordDocument.VerificationStatus.VERIFIED,
        )
    )
    return Property.objects.filter(
        verified_docs_q,
        publication_status=Property.PublicationStatus.PUBLISHED,
        verification_status=Property.VerificationStatus.VERIFIED,
        is_available=True,
    ).distinct().select_related(
        "region",
        "district",
        "town",
        "area",
    ).prefetch_related(
        "amenities",
        "media",
    )


def _apply_filters(qs, filters):
    """
    Apply user-selected filters to a Property queryset.
    `filters` is a dict of cleaned values coming from request.GET.
    Unknown / empty values are ignored.
    """
    # Free-text search (title / description / location names)
    q = (filters.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(region__name__icontains=q)
            | Q(district__name__icontains=q)
            | Q(town__name__icontains=q)
            | Q(area__name__icontains=q)
        ).distinct()

    # Location filters — accept either a pk or a slug
    region = (filters.get("region") or "").strip()
    if region:
        qs = qs.filter(Q(region__pk=region) | Q(region__slug=region))

    district = (filters.get("district") or "").strip()
    if district:
        qs = qs.filter(Q(district__pk=district) | Q(district__slug=district))

    town = (filters.get("town") or "").strip()
    if town:
        qs = qs.filter(Q(town__pk=town) | Q(town__slug=town))

    area = (filters.get("area") or "").strip()
    if area:
        qs = qs.filter(Q(area__pk=area) | Q(area__slug=area))

    # Property type / room type
    room_type = (filters.get("room_type") or "").strip()
    if room_type:
        qs = qs.filter(room_type=room_type)

    # Payment period
    payment_period = (filters.get("payment_period") or "").strip()
    if payment_period:
        qs = qs.filter(payment_period=payment_period)

    # Price range
    min_price = filters.get("min_price")
    if min_price not in (None, ""):
        try:
            qs = qs.filter(price__gte=float(min_price))
        except (TypeError, ValueError):
            pass

    max_price = filters.get("max_price")
    if max_price not in (None, ""):
        try:
            qs = qs.filter(price__lte=float(max_price))
        except (TypeError, ValueError):
            pass

    # Bedrooms (minimum)
    bedrooms = filters.get("bedrooms")
    if bedrooms not in (None, "", "any"):
        try:
            qs = qs.filter(bedrooms__gte=int(bedrooms))
        except (TypeError, ValueError):
            pass

    # Furnished
    if filters.get("furnished") == "1" and not filters.get("unfurnished"):
        qs = qs.filter(is_furnished=True)
    elif filters.get("unfurnished") == "1" and not filters.get("furnished"):
        qs = qs.filter(is_furnished=False)
    # If both are checked (or neither), no filter is applied.

    return qs


def get_published_properties(filters=None):
    """
    Return the list of published+verified+available properties.
    If `filters` is given, it is passed to `_apply_filters` first.
    """
    qs = _property_queryset()
    if filters:
        qs = _apply_filters(qs, filters)
    return list(qs.order_by("-created_at"))


def get_filtered_properties_count(filters):
    """Return the count of properties matching the filters, ignoring pagination."""
    qs = _property_queryset()
    if filters:
        qs = _apply_filters(qs, filters)
    return qs.count()


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