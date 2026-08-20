"""
Context processors for the ``tenant`` app.

These inject data into the template context on **every** request, so they
must be cheap. The ``saved_count`` processor is used by the sidebar in
``tenant/base.html`` to display a live count of properties the logged-in
tenant has saved, and the ``recent_saved_properties`` processor powers the
"Recently Saved" mini-list in the sidebar.

``tenant_sidebar_counts`` consolidates the smaller badges (property views,
property alerts, viewing requests + pending viewing requests) into a
single processor so we don't fan out to a handful of separate cache
lookups on every request.
"""

from django.core.cache import cache

from apps.tenant.models import PropertyAlert, PropertyView, SavedProperty, ViewingRequest


def saved_count(request):
    """
    Adds ``saved_count`` to the context for any logged-in tenant.

    Falls back to ``0`` for anonymous users, landlords, or anyone else
    browsing a tenant page (e.g. when an admin previews a tenant screen).
    The count is cached for 1 hour per tenant and is invalidated by
    :func:`apps.tenant.views.toggle_saved_property_view` on every save /
    unsave action.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or getattr(user, "role", None) != user.Role.TENANT:
        return {"saved_count": 0, "has_saved_properties": False}

    cache_key = f"tenant:saved_count:{user.pk}"
    count = cache.get(cache_key)
    if count is None:
        count = SavedProperty.objects.filter(tenant=user).count()
        cache.set(cache_key, count, timeout=60 * 60)

    return {
        "saved_count": count,
        "has_saved_properties": count > 0,
    }


def recent_saved_properties(request):
    """
    Adds ``recent_saved_properties`` (a list of up to 4 ``SavedProperty``
    rows, with related ``Property`` prefetched) to the context.

    Used by the sidebar in ``tenant/base.html`` to render the "Recently
    Saved" mini-list. Empty for non-tenant users. Cached for 1 hour per
    tenant; invalidated on save / unsave by
    :func:`apps.tenant.views.toggle_saved_property_view`.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or getattr(user, "role", None) != user.Role.TENANT:
        return {"recent_saved_properties": []}

    cache_key = f"tenant:recent_saved_properties:{user.pk}"
    items = cache.get(cache_key)
    if items is None:
        items = list(
            SavedProperty.objects.filter(tenant=user)
            .select_related("property", "property__region", "property__district", "property__area")
            .order_by("-created_at")[:4]
        )
        cache.set(cache_key, items, timeout=60 * 60)

    return {"recent_saved_properties": items}


def tenant_sidebar_counts(request):
    """
    Adds ``views_count``, ``alerts_count``, ``requests_count`` and
    ``pending_requests_count`` to the context for any logged-in tenant.

    All four are read in a single pass through the cache to keep the
    sidebar cheap. Values default to ``0`` for anonymous users, landlords
    or admins browsing a tenant page (e.g. when an admin previews the
    tenant dashboard).

    The four cache keys are invalidated by the views that mutate the
    underlying rows:

      * ``tenant:sidebar_counts:{user_id}``  — wholesale invalidation
        on any change to views / alerts / viewing requests (used by
        the views when something is added, removed, or status-changed).

    Counters cached individually would let us invalidate more precisely,
    but in practice a tenant changing any of these numbers is rare
    enough that a single shared cache key is fine and keeps the
    processor's read pattern to two cache lookups (the shared key + the
    existing saved_count key).
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or getattr(user, "role", None) != user.Role.TENANT:
        return {
            "views_count": 0,
            "alerts_count": 0,
            "requests_count": 0,
            "pending_requests_count": 0,
        }

    cache_key = f"tenant:sidebar_counts:{user.pk}"
    counts = cache.get(cache_key)
    if counts is None:
        counts = {
            "views_count": PropertyView.objects.filter(tenant=user).count(),
            "alerts_count": PropertyAlert.objects.filter(tenant=user, is_active=True).count(),
            "requests_count": ViewingRequest.objects.filter(tenant=user).count(),
            "pending_requests_count": ViewingRequest.objects.filter(
                tenant=user, status=ViewingRequest.Status.PENDING
            ).count(),
        }
        # 1-hour TTL keeps the sidebar fresh without hammering the DB;
        # mutations to the underlying tables invalidate the key eagerly
        # (see the views in apps/tenant/views.py).
        cache.set(cache_key, counts, timeout=60 * 60)

    return counts


def saved_property_ids(request):
    """
    Adds ``saved_property_ids`` (a dict keyed by ``str(property.id)`` for
    fast ``{% if id in saved_property_ids %}`` lookups) to the context
    for any logged-in tenant.

    Used by the public-facing home_finder pages (index, property_list,
    property_detail) to render the heart icon in its filled-vs-outline
    state, and to wire the heart button to the tenant's toggle-save
    endpoint. Empty for anonymous users, landlords, or admins browsing.

    The set is cached for 1 hour per tenant and invalidated by
    :func:`apps.tenant.views.toggle_saved_property_view` on every save
    or unsave action.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or getattr(user, "role", None) != user.Role.TENANT:
        return {"saved_property_ids": {}}

    cache_key = f"tenant:saved_property_ids:{user.pk}"
    ids = cache.get(cache_key)
    if ids is None:
        ids = {
            str(sp.property_id): True
            for sp in SavedProperty.objects.filter(tenant=user).only("property_id")
        }
        cache.set(cache_key, ids, timeout=60 * 60)

    return {"saved_property_ids": ids}
