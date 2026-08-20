"""
Selectors for the landlord side of the viewing-request pipeline.

Kept separate from ``apps/landloards/views.py`` so the read logic can be
unit-tested without spinning up a request cycle, and so the same queries
can be shared between the list view, the dashboard summary, and any
future API endpoint that surfaces a landlord's viewing-request inbox.

All functions take a landlord ``User`` instance and return either a
list / single ``ViewingRequest`` or a small dict of summary counts.
Caching is per-landlord with a short TTL (5 minutes) — viewing
requests are low-volume per landlord but the dashboard hits the count
on every page render, so a single cached aggregate is well worth it.
Mutations in ``apps/landloards/views.py`` invalidate the cache key
eagerly so the badge stays accurate.
"""
from __future__ import annotations

from django.core.cache import cache

from apps.tenant.models import ViewingRequest


LANDLORD_VIEWING_REQUESTS_CACHE_TTL = 60 * 5  # 5 minutes
LANDLORD_VIEWING_REQUESTS_CACHE_PREFIX = "landlord:viewing_requests"


def _cache_key(landlord_id, suffix: str) -> str:
    return f"{LANDLORD_VIEWING_REQUESTS_CACHE_PREFIX}:{landlord_id}:{suffix}"


def get_landlord_viewing_requests(landlord):
    """
    Return every ``ViewingRequest`` whose ``property.landlord`` is the
    given landlord, newest preferred-date first.

    Includes the related ``tenant``, ``property`` and location rows so
    the list template can render the row in a single query.
    """
    cache_key = _cache_key(landlord.pk, "list")
    requests = cache.get(cache_key)
    if requests is None:
        requests = list(
            ViewingRequest.objects
            .filter(property__landlord=landlord)
            .select_related(
                "tenant",
                "property",
                "property__region",
                "property__district",
                "property__area",
            )
            .order_by("-preferred_date", "-preferred_time", "-created_at")
        )
        cache.set(cache_key, requests, timeout=LANDLORD_VIEWING_REQUESTS_CACHE_TTL)
    return requests


def get_landlord_viewing_request(landlord, request_id):
    """
    Return a single ``ViewingRequest`` for this landlord, or ``None`` if
    it doesn't exist (or belongs to another landlord). Used by the
    confirm/decline/reschedule views to enforce ownership in one place.
    """
    return (
        ViewingRequest.objects
        .select_related(
            "tenant", "property", "property__region",
            "property__district", "property__area",
        )
        .filter(pk=request_id, property__landlord=landlord)
        .first()
    )


def get_landlord_pending_viewing_request_count(landlord) -> int:
    """Count of pending viewing requests for the landlord's properties."""
    cache_key = _cache_key(landlord.pk, "pending_count")
    count = cache.get(cache_key)
    if count is None:
        count = ViewingRequest.objects.filter(
            property__landlord=landlord,
            status=ViewingRequest.Status.PENDING,
        ).count()
        cache.set(cache_key, count, timeout=LANDLORD_VIEWING_REQUESTS_CACHE_TTL)
    return count


def get_landlord_viewing_request_counts(landlord) -> dict:
    """
    Aggregate status counts for the landlord dashboard / sidebar badge.
    Returns::

        {
            "pending_count": int,
            "confirmed_count": int,
            "completed_count": int,
            "cancelled_count": int,
            "total_count": int,
        }
    """
    from django.db.models import Count, Q
    cache_key = _cache_key(landlord.pk, "counts")
    counts = cache.get(cache_key)
    if counts is None:
        base = ViewingRequest.objects.filter(property__landlord=landlord)
        counts = base.aggregate(
            pending_count=Count("id", filter=Q(status=ViewingRequest.Status.PENDING)),
            confirmed_count=Count("id", filter=Q(status=ViewingRequest.Status.CONFIRMED)),
            completed_count=Count("id", filter=Q(status=ViewingRequest.Status.COMPLETED)),
            cancelled_count=Count("id", filter=Q(status=ViewingRequest.Status.CANCELLED)),
            total_count=Count("id"),
        )
        cache.set(cache_key, counts, timeout=LANDLORD_VIEWING_REQUESTS_CACHE_TTL)
    return counts


def invalidate_landlord_viewing_requests_cache(landlord_id) -> None:
    """
    Drop every cached selector for this landlord. Called from views
    whenever a viewing-request row is created, mutated, or its status
    changes — the badge counts and list must reflect reality on the
    next request, so we delete instead of waiting for TTL expiry.
    """
    cache.delete_many([
        _cache_key(landlord_id, "list"),
        _cache_key(landlord_id, "pending_count"),
        _cache_key(landlord_id, "counts"),
    ])
