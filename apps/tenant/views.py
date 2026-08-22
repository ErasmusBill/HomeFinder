from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.account.models import User
from apps.home_finder.models import Property
from apps.locations.models import District, Region
from apps.notifications.models import Notification
from apps.tenant.forms import PropertyAlertForm, ViewingRequestForm
from apps.tenant.models import PropertyAlert, PropertyView, SavedProperty, ViewingRequest
from apps.tenant.selectors import get_property_alerts_cache_key, get_tenant_saved_properties, get_tenant_property_views, get_tenant_property_alerts, get_tenant_viewing_requests, get_viewing_requests_cache_key

def tenant_required(request):
    return request.user.is_authenticated and (request.user.role == request.user.Role.TENANT)

def tenant_forbidden():
    return render(request=None, template_name="403.html", status=403)

def record_property_view(tenant, property_obj):
    PropertyView.objects.update_or_create(tenant=tenant, property=property_obj, defaults={})

@login_required
def tenant_dashboard_view(request):
    if not tenant_required(request):
        return render(request, "403.html", status=403)
    tenant = request.user

    saved_properties = get_tenant_saved_properties(tenant)
    property_views = get_tenant_property_views(tenant)
    property_alerts = get_tenant_property_alerts(tenant)
    viewing_requests = get_tenant_viewing_requests(tenant)

    recommended_properties = Property.objects.filter(is_available=True).select_related("region", "district", "area").prefetch_related("media").order_by("-created_at")[:6]

    upcoming_viewings = [viewing for viewing in viewing_requests if viewing.status in [ViewingRequest.Status.PENDING, ViewingRequest.Status.CONFIRMED]][:3]

    # First name for the greeting (split full_name on the first whitespace).
    full_name = (tenant.full_name or "").strip()
    first_name = full_name.split(" ", 1)[0] if full_name else "there"

    # "Active Search" region label: prefer the most recent active alert's
    # region/district, otherwise fall back to the most recently saved
    # property's location. If nothing exists yet, fall back to None and
    # the template will hide the chip gracefully.
    active_search_label = None
    if property_alerts:
        latest_alert = property_alerts[0]
        parts = [latest_alert.region.name if latest_alert.region else None, latest_alert.district.name if latest_alert.district else None, latest_alert.area.name if latest_alert.area else None]
        active_search_label = ", ".join(p for p in parts if p) or None
    elif saved_properties:
        latest = saved_properties[0]
        parts = [latest.property.area.name if latest.property.area else None, latest.property.region.name if latest.property.region else None]
        active_search_label = ", ".join(p for p in parts if p) or None

    context = {"saved_count": len(saved_properties), "views_count": len(property_views), "alerts_count": len(property_alerts), "requests_count": len(viewing_requests), "saved_properties": saved_properties[:4], "property_views": property_views[:4], "property_alerts": property_alerts[:3], "upcoming_viewings": upcoming_viewings, "recommended_properties": recommended_properties, "tenant": tenant, "first_name": first_name, "active_search_label": active_search_label}
    return render(request, "tenant/dashboard.html", context)

@login_required
def saved_properties_list_view(request):
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    # ------------------------------------------------------------------ #
    # Read query-string filters/sort/layout                             #
    # ------------------------------------------------------------------ #
    sort = request.GET.get("sort", "recent")               # recent | price_asc | price_desc
    region_id = request.GET.get("region") or ""
    district_id = request.GET.get("district") or ""
    room_type = request.GET.get("room_type") or ""
    view_layout = request.GET.get("view", "grid")         # grid | list
    page_num = request.GET.get("page", 1)

    # ------------------------------------------------------------------ #
    # Build the filtered queryset (NOT cached — depends on user input)   #
    # ------------------------------------------------------------------ #
    qs = (
        SavedProperty.objects
        .filter(tenant=request.user)
        .select_related("property", "property__region", "property__district", "property__area")
    )

    property_filters = Q()
    if region_id:
        property_filters &= Q(property__region_id=region_id)
        # If a region is chosen, narrow districts to those in that region.
        districts_qs = District.objects.filter(region_id=region_id)
    else:
        districts_qs = District.objects.all()

    if district_id:
        property_filters &= Q(property__district_id=district_id)

    if room_type:
        property_filters &= Q(property__room_type=room_type)

    qs = qs.filter(property_filters)

    # Apply sort. We always keep a deterministic tiebreaker on created_at
    # so pagination is stable when prices match.
    if sort == "price_asc":
        qs = qs.order_by("property__price", "-created_at")
    elif sort == "price_desc":
        qs = qs.order_by("-property__price", "-created_at")
    else:
        qs = qs.order_by("-created_at")

    saved_properties = list(qs)

    # ------------------------------------------------------------------ #
    # Pagination                                                         #
    # ------------------------------------------------------------------ #
    from django.core.paginator import Paginator
    paginator = Paginator(saved_properties, 12)  # 12 cards per page
    try:
        page_num = int(page_num)
    except (TypeError, ValueError):
        page_num = 1
    if page_num < 1:
        page_num = 1
    if page_num > paginator.num_pages and paginator.num_pages > 0:
        page_num = paginator.num_pages

    page_obj = paginator.get_page(page_num)

    # ------------------------------------------------------------------ #
    # Facet data: regions, districts (region-filtered), room types        #
    # ------------------------------------------------------------------ #
    regions = Region.objects.all().order_by("name")
    room_type_choices = Property.RoomType.choices

    # Count of saved properties (ignores current filters) for the header
    # subtitle.
    total_saved_count = SavedProperty.objects.filter(tenant=request.user).count()

    # Persist current query string so pagination / clear-all can keep state.
    querystring = request.GET.copy()
    querystring.pop("page", None)

    context = {
        "saved_properties": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "saved_count": total_saved_count,
        # Filter dropdown data
        "regions": regions,
        "districts": districts_qs,
        "room_type_choices": room_type_choices,
        # Echo back current selections so the form preserves state
        "current_sort": sort,
        "current_region": region_id,
        "current_district": district_id,
        "current_room_type": room_type,
        "current_view": view_layout,
        "querystring": querystring.urlencode(),
    }
    return render(request, "tenant/saved_properties.html", context)


@login_required
@require_POST
def clear_saved_properties_view(request):
    """Removes every SavedProperty row for the logged-in tenant."""
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    SavedProperty.objects.filter(tenant=request.user).delete()

    from apps.tenant.selectors import get_saved_properties_cache_key
    cache.delete_many([
        get_saved_properties_cache_key(request.user.pk),
        f"tenant:saved_count:{request.user.pk}",
        f"tenant:recent_saved_properties:{request.user.pk}",
    ])

    return redirect("tenant:saved_properties_list")

@login_required
@require_POST
def toggle_saved_property_view(request, property_id):

    if not tenant_required(request):
        return render(request, "403.html", status=403)

    property_obj = get_object_or_404(Property, pk=property_id)

    saved_property = SavedProperty.objects.filter(tenant=request.user, property=property_obj).first()

    if saved_property:
        saved_property.delete()
    else:
        SavedProperty.objects.create(tenant=request.user, property=property_obj)

    # Invalidate the cached saved-properties list, the sidebar count, and
    # the recent-saved-properties set so the sidebar badge, sidebar mini
    # list, and dashboard hearts all reflect the new state on the next
    # request.
    from apps.tenant.selectors import get_saved_properties_cache_key
    cache.delete_many([
        get_saved_properties_cache_key(request.user.pk),
        f"tenant:saved_count:{request.user.pk}",
        f"tenant:recent_saved_properties:{request.user.pk}",
    ])

    return redirect(request.META.get("HTTP_REFERER", "tenant:dashboard"))

@login_required
def property_views_list_view(request):
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    # ------------------------------------------------------------------ #
    # Read query-string filters/sort                                    #
    # ------------------------------------------------------------------ #
    sort = request.GET.get("sort", "recent")          # recent | price_asc | price_desc
    region_id = request.GET.get("region") or ""
    room_type = request.GET.get("room_type") or ""
    page_num = request.GET.get("page", 1)

    # ------------------------------------------------------------------ #
    # Build filtered queryset (NOT cached — depends on user input)      #
    # ------------------------------------------------------------------ #
    qs = (
        PropertyView.objects
        .filter(tenant=request.user)
        .select_related("property", "property__region", "property__district", "property__area")
    )

    filters = Q()
    if region_id:
        filters &= Q(property__region_id=region_id)
    if room_type:
        filters &= Q(property__room_type=room_type)
    qs = qs.filter(filters)

    if sort == "price_asc":
        qs = qs.order_by("property__price", "-viewed_at")
    elif sort == "price_desc":
        qs = qs.order_by("-property__price", "-viewed_at")
    else:  # "recent" default
        qs = qs.order_by("-viewed_at")

    property_views = list(qs)

    # ------------------------------------------------------------------ #
    # Pagination                                                          #
    # ------------------------------------------------------------------ #
    from django.core.paginator import Paginator
    paginator = Paginator(property_views, 12)
    try:
        page_num = int(page_num)
    except (TypeError, ValueError):
        page_num = 1
    page_obj = paginator.get_page(page_num)

    # ------------------------------------------------------------------ #
    # Facet data: regions, room types                                   #
    # ------------------------------------------------------------------ #
    regions = Region.objects.all().order_by("name")
    room_type_choices = Property.RoomType.choices

    querystring = request.GET.copy()
    querystring.pop("page", None)

    context = {
        "property_views": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "views_count": len(property_views),
        "regions": regions,
        "room_type_choices": room_type_choices,
        "current_sort": sort,
        "current_region": region_id,
        "current_room_type": room_type,
        "querystring": querystring.urlencode(),
    }
    return render(request, "tenant/property_views.html", context)

@login_required
@require_POST
def clear_property_views_view(request):
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    PropertyView.objects.filter(tenant=request.user).delete()

    return redirect("tenant:property_views")

@login_required
def tenant_property_detail_view(request, property_id):
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    property_obj = get_object_or_404(Property.objects.select_related("region", "district", "area").prefetch_related("media"), pk=property_id)

    record_property_view(tenant=request.user, property_obj=property_obj)
    is_saved = SavedProperty.objects.filter(tenant=request.user, property=property_obj).exists()
    viewing_requests = ViewingRequest.objects.filter(tenant=request.user, property=property_obj).order_by("-preferred_date", "-preferred_time")
    cache.delete(f"tenant:sidebar_counts:{request.user.pk}")

    context = {"property": property_obj, "is_saved": is_saved, "viewing_requests": viewing_requests}
    return render(request, "tenant/property_detail.html", context)

@login_required
def property_alerts_list_create_view(request):

    if not tenant_required(request):
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = PropertyAlertForm(request.POST)
        if form.is_valid():
            alert = form.save(commit=False)
            alert.tenant = request.user
            alert.save()
            # New alert created -> invalidate cached alert list/summary so the
            # counts and sidebar refresh on the next request.
            cache.delete_many([
                get_property_alerts_cache_key(request.user.pk),
                f"tenant:alerts_count:{request.user.pk}",
            ])
            return redirect("tenant:property_alerts")
    else:
        form = PropertyAlertForm()

    # Read sort filter from query string (newest | oldest | active | paused).
    sort = request.GET.get("sort", "newest")

    # Pull all alerts (active + paused) so the user can manage both; the
    # selector previously hid paused rows.
    alerts_qs = (
        PropertyAlert.objects
        .filter(tenant=request.user)
        .select_related("region", "district", "area")
    )

    if sort == "oldest":
        alerts_qs = alerts_qs.order_by("created_at")
    elif sort == "active":
        alerts_qs = alerts_qs.order_by("-is_active", "-created_at")
    elif sort == "paused":
        alerts_qs = alerts_qs.order_by("is_active", "-created_at")
    else:  # "newest" default
        alerts_qs = alerts_qs.order_by("-created_at")

    alerts = list(alerts_qs)

    # Real DB counts for the stat cards.
    from django.db.models import Count, Q
    base_qs = PropertyAlert.objects.filter(tenant=request.user)
    counts = base_qs.aggregate(
        active_count=Count("id", filter=Q(is_active=True)),
        paused_count=Count("id", filter=Q(is_active=False)),
        total_count=Count("id"),
    )
    active_count = counts["active_count"]
    paused_count = counts["paused_count"]
    total_count = counts["total_count"]

    context = {
        "form": form,
        "alerts": alerts,
        "alerts_count": active_count,
        "active_count": active_count,
        "paused_count": paused_count,
        "total_count": total_count,
        "current_sort": sort,
    }

    return render(request, "tenant/property_alerts.html", context)

@login_required
def update_property_alert_view(request, alert_id):

    if not tenant_required(request):
        return render(request, "403.html", status=403)
    alert = get_object_or_404(PropertyAlert, pk=alert_id, tenant=request.user)

    if request.method == "POST":
        form = PropertyAlertForm(request.POST, instance=alert)
        if form.is_valid():
            updated_alert = form.save(commit=False)
            updated_alert.tenant = request.user
            updated_alert.save()
            cache.delete_many([
                get_property_alerts_cache_key(request.user.pk),
                f"tenant:alerts_count:{request.user.pk}",
            ])
            return redirect("tenant:property_alerts")
    else:
        form = PropertyAlertForm(instance=alert)
    context = {"form": form, "alert": alert, "is_update": True}
    return render(request, "tenant/property_alert_form.html", context)

@login_required
@require_POST
def delete_property_alert_view(request, alert_id):
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    alert = get_object_or_404(PropertyAlert, pk=alert_id, tenant=request.user)
    alert.delete()
    cache.delete_many([
        get_property_alerts_cache_key(request.user.pk),
        f"tenant:alerts_count:{request.user.pk}",
    ])
    return redirect("tenant:property_alerts")

@login_required
@require_POST
def toggle_property_alert_view(request, alert_id):
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    alert = get_object_or_404(PropertyAlert, pk=alert_id, tenant=request.user)
    alert.is_active = not alert.is_active
    alert.save(update_fields=["is_active"])

    cache.delete_many([
        get_property_alerts_cache_key(request.user.pk),
        f"tenant:alerts_count:{request.user.pk}",
    ])

    return redirect("tenant:property_alerts")

@login_required
def viewing_requests_list_create_view(request, property_id=None):
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    # ``property_obj`` is resolved from the URL when the user lands on
    # the per-property endpoint (``/properties/<id>/request-viewing/``).
    # When the user lands on the bare list endpoint
    # (``/tenants/viewing-requests/``) and submits the inline form, the
    # chosen property comes from the form's ``property`` field instead.
    property_obj = None
    if property_id:
        property_obj = get_object_or_404(Property, pk=property_id)

    if request.method == "POST":
        form = ViewingRequestForm(request.POST)
        if form.is_valid():
            viewing_request = form.save(commit=False)
            viewing_request.tenant = request.user
            # Prefer the URL's property_id (it's the source of truth on
            # the per-property page); fall back to the value the tenant
            # picked in the form's dropdown on the list page.
            if property_obj:
                viewing_request.property = property_obj
            elif viewing_request.property_id:
                viewing_request.property = Property.objects.get(pk=viewing_request.property_id)
            viewing_request.save()
            # New viewing request -> invalidate sidebar count cache.
            cache.delete(f"tenant:sidebar_counts:{request.user.pk}")
            # Notify the landlord (email + in-app) that a tenant just
            # created a viewing request on their property.
            from apps.landloards.tasks import (
                notify_landlord_viewing_request_created_task,
            )
            notify_landlord_viewing_request_created_task.delay(
                str(viewing_request.pk),
            )
            messages.success(request, "Viewing request submitted. The landlord has been notified.")
            return redirect("tenant:viewing_requests")
        # else: fall through to re-render the page with the bound form
        # so the user sees the validation errors.
    else:
        # When the URL carries a property_id we pre-bind the form's
        # property field to that property and hide the dropdown, since
        # the property is already implied by the page context.
        if property_obj:
            form = ViewingRequestForm(initial={"property": property_obj})
            form.fields["property"].widget = forms.HiddenInput()
        else:
            form = ViewingRequestForm()
    # ------------------------------------------------------------------ #
    # Status filter from query string (all | pending | confirmed | completed | cancelled)
    # ------------------------------------------------------------------ #
    status_filter = request.GET.get("status", "all")

    qs = (
        ViewingRequest.objects
        .filter(tenant=request.user)
        .select_related("property", "property__region", "property__district", "property__area")
    )

    if status_filter in ViewingRequest.Status.values:
        qs = qs.filter(status=status_filter)

    qs = qs.order_by("-preferred_date", "-preferred_time", "-created_at")
    viewing_requests = list(qs)

    # Stat-card counts (read live so the page always shows the current
    # status breakdown, even after a recent cancel/reschedule). These
    # stay independent of the active filter so users always see their
    # real totals.
    from django.db.models import Count, Q as _Q
    status_breakdown = ViewingRequest.objects.filter(tenant=request.user).aggregate(
        confirmed_count=Count("id", filter=_Q(status=ViewingRequest.Status.CONFIRMED)),
        pending_count=Count("id", filter=_Q(status=ViewingRequest.Status.PENDING)),
        completed_count=Count("id", filter=_Q(status=ViewingRequest.Status.COMPLETED)),
        total_count=Count("id"),
    )

    context = {
        "form": form,
        "property": property_obj,
        "viewing_requests": viewing_requests,
        "current_status": status_filter,
        "status_choices": ViewingRequest.Status.choices,
        **status_breakdown,
    }
    return render(request, "tenant/viewing_requests.html", context)

@login_required
@require_POST
def cancel_viewing_request_view(request, request_id):
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    viewing_request = get_object_or_404(ViewingRequest, pk=request_id, tenant=request.user)

    allowed_statuses = [ViewingRequest.Status.PENDING, ViewingRequest.Status.CONFIRMED]

    if viewing_request.status in allowed_statuses:
        previous_status = viewing_request.status
        viewing_request.status = ViewingRequest.Status.CANCELLED
        viewing_request.save(update_fields=["status"])

        # Invalidate landlord-side caches so the inbox / badge reflects
        # the cancellation immediately.
        from apps.landloards.selectors import (
            invalidate_landlord_viewing_requests_cache,
        )
        invalidate_landlord_viewing_requests_cache(
            viewing_request.property.landlord_id,
        )

        # Notify the landlord that the tenant cancelled.
        from apps.landloards.tasks import (
            notify_landlord_viewing_request_cancelled_task,
        )
        notify_landlord_viewing_request_cancelled_task.delay(
            str(viewing_request.pk), previous_status,
        )

    cache.delete(f"tenant:sidebar_counts:{request.user.pk}")
    return redirect("tenant:viewing_requests")


@login_required
def update_viewing_request_view(request, request_id):
    """
    Tenant edits the date / time / notes on one of their own viewing
    requests. Only allowed while the request is still ``pending`` — once
    the landlord confirms, the tenant must cancel + re-create instead
    (otherwise the landlord's calendar gets out of sync with what the
    tenant sees).

    On a successful update we queue a reschedule notification so the
    landlord sees the new proposed time in their dashboard and email.
    """
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    viewing_request = get_object_or_404(
        ViewingRequest.objects.select_related("property", "property__landlord", "property__region", "property__district", "property__area"),
        pk=request_id, tenant=request.user,
    )

    if viewing_request.status != ViewingRequest.Status.PENDING:
        from django.contrib import messages
        messages.warning(
            request,
            "This viewing request can no longer be edited. Cancel it and "
            "submit a new one if your plans have changed.",
        )
        return redirect("tenant:viewing_requests")

    if request.method == "POST":

        form = ViewingRequestForm(
            request.POST, instance=viewing_request, exclude_property=True,
        )
        if form.is_valid():
            # Capture the previous date/time so we can include it in the
            # landlord notification for context.
            previous_date = viewing_request.preferred_date
            previous_time = viewing_request.preferred_time
            updated = form.save(commit=False)
            # Defensive: ensure the tenant can't "move" the request to
            # another property even if they tamper with hidden inputs.
            updated.tenant = request.user
            updated.property = viewing_request.property
            updated.status = ViewingRequest.Status.PENDING
            updated.save()
            cache.delete(f"tenant:sidebar_counts:{request.user.pk}")

            # Tell the landlord that the tenant just rescheduled.
            from apps.landloards.tasks import (
                notify_landlord_viewing_request_rescheduled_task,
            )
            notify_landlord_viewing_request_rescheduled_task.delay(
                str(updated.pk),
                previous_date.isoformat() if previous_date else "",
                previous_time.isoformat() if previous_time else "",
            )
            from django.contrib import messages
            messages.success(request, "Viewing request updated. The landlord has been notified.")
            return redirect("tenant:viewing_requests")
    else:
        form = ViewingRequestForm(
            instance=viewing_request,
            initial={
                "preferred_date": viewing_request.preferred_date,
                "preferred_time": viewing_request.preferred_time,
                "notes": viewing_request.notes or "",
            },
            exclude_property=True,
        )

    context = {
        "form": form,
        "viewing_request": viewing_request,
        "is_update": True,
    }
    return render(request, "tenant/viewing_request_form.html", context)

@login_required
def viewing_request_detail_view(request, request_id):
    if not tenant_required(request): return render(request, "403.html", status=403)
    viewing_request = get_object_or_404(ViewingRequest.objects.select_related("property", "property__region", "property__district", "property__area"), pk=request_id, tenant=request.user)
    context = {"viewing_request": viewing_request}
    return render(request, "tenant/viewing_request_detail.html", context)


@login_required
@require_POST
def delete_viewing_request_view(request, request_id):
    """
    Permanently remove a viewing request owned by the current tenant.

    The request is fully deleted (not soft-cancelled). Use this when the
    tenant no longer wants the request to appear in their list at all
    (e.g. the property was withdrawn, they found another home, or they
    just want a clean history).

    Any in-app notifications whose ``target`` points at the underlying
    Property are intentionally left alone - they reference the Property,
    not the ViewingRequest, so they remain useful historical record
    tied to the listing itself.
    """
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    viewing_request = get_object_or_404(
        ViewingRequest, pk=request_id, tenant=request.user,
    )

    # Keep a couple of useful breadcrumbs for the flash message + the
    # landlord-cache invalidation.
    landlord_id = viewing_request.property.landlord_id
    property_title = viewing_request.property.title

    viewing_request.delete()

    from apps.landloards.selectors import (
        invalidate_landlord_viewing_requests_cache,
    )
    cache.delete_many([
        get_viewing_requests_cache_key(request.user.pk),
        f"tenant:sidebar_counts:{request.user.pk}",
    ])
    invalidate_landlord_viewing_requests_cache(landlord_id)

    messages.success(
        request,
        f"Viewing request for \"{property_title}\" was deleted.",
    )
    return redirect("tenant:viewing_requests")


@login_required
def tenant_notifications_detail_view(request, user_id):
    """
    Full-stack view for an admin or landlord to view all notifications
    related to a specific tenant (by recipient, sender, or GFK target).

    Query-string filters:
        ``status`` — ``all`` (default), ``read``, or ``unread``.
    """
    tenant = get_object_or_404(User, pk=user_id)

    # Read filter (all | read | unread). ``all`` is the default and
    # preserves backwards compatibility with the original page.
    status_filter = request.GET.get("status", "all")
    if status_filter not in ("all", "read", "unread"):
        status_filter = "all"

    # Fetch notification logic
    tenant_type = ContentType.objects.get_for_model(tenant)
    user = getattr(tenant, 'user', tenant)

    notifications = Notification.objects.filter(
        Q(user=user) |
        Q(created_by=user) |
        Q(content_type=tenant_type, object_id=str(tenant.pk))
    ).select_related('user', 'created_by').distinct()

    if status_filter == "read":
        notifications = notifications.filter(is_read=True)
    elif status_filter == "unread":
        notifications = notifications.filter(is_read=False)

    # Order newest-first so the page reads top-down chronologically.
    notifications = notifications.order_by("-created_at")

    # Live counts (independent of the active filter) so the status
    # pills always show the real totals.
    base_qs = Notification.objects.filter(
        Q(user=user) |
        Q(created_by=user) |
        Q(content_type=tenant_type, object_id=str(tenant.pk))
    ).distinct()
    from django.db.models import Count, Q as _Q
    counts = base_qs.aggregate(
        all_count=Count("id"),
        read_count=Count("id", filter=_Q(is_read=True)),
        unread_count=Count("id", filter=_Q(is_read=False)),
    )

    # Persist current query string so "clear filter" can keep other params.
    querystring = request.GET.copy()
    querystring.pop("status", None)

    context = {
        'tenant': tenant,
        'notifications': notifications,
        'current_status': status_filter,
        'all_count': counts["all_count"],
        'read_count': counts["read_count"],
        'unread_count': counts["unread_count"],
        'querystring': querystring.urlencode(),
    }

    return render(request, 'tenant/tenant_notifications_list.html', context)


@login_required
def my_tenant_notifications_view(request):
    """
    Full-stack view for a logged-in tenant to see their own related notifications.

    Query-string filters:
        ``status`` — ``all`` (default), ``read``, or ``unread``.

    Paginated 20 per page so long notification histories don't render the
    whole page server-side.
    """
    current_user = request.user

    status_filter = request.GET.get("status", "all")
    if status_filter not in ("all", "read", "unread"):
        status_filter = "all"

    # Tenants only see notifications addressed TO them. We deliberately
    # don't include ``created_by=current_user`` here because tenants don't
    # author notifications in this app — that branch was leftover from
    # the landlord logic and was inflating the count with self-references.
    base_qs = Notification.objects.filter(user=current_user).select_related('user', 'created_by')

    # Apply the read-state filter for the displayed page.
    if status_filter == "read":
        page_qs = base_qs.filter(is_read=True)
    elif status_filter == "unread":
        page_qs = base_qs.filter(is_read=False)
    else:
        page_qs = base_qs.all()

    page_qs = page_qs.order_by("-created_at")

    # Pagination (20 per page).
    from django.core.paginator import Paginator
    paginator = Paginator(page_qs, 20)
    try:
        page_num = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page_num = 1
    if page_num < 1:
        page_num = 1
    if page_num > paginator.num_pages and paginator.num_pages > 0:
        page_num = paginator.num_pages
    page_obj = paginator.get_page(page_num)

    # Counts stay on the unfiltered queryset so the tab pills always
    # show the real totals, regardless of which tab is active.
    from django.db.models import Count
    counts = base_qs.aggregate(
        all_count=Count("id"),
        read_count=Count("id", filter=Q(is_read=True)),
        unread_count=Count("id", filter=Q(is_read=False)),
    )

    # Preserve non-status params (page) when toggling the filter.
    querystring = request.GET.copy()
    querystring.pop("status", None)
    querystring.pop("page", None)

    context = {
        'notifications': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'current_status': status_filter,
        'all_count': counts["all_count"],
        'read_count': counts["read_count"],
        'unread_count': counts["unread_count"],
        'querystring': querystring.urlencode(),
    }

    return render(request, 'tenant/my_notifications.html', context)


# ---------------------------------------------------------------------------
# Tenant notification actions (mark read / mark unread / delete / clear all)
# ---------------------------------------------------------------------------
# All actions below are POST-only and resolve the notification through a
# tenant-scoped queryset so a tenant can never read/delete someone else's
# notification just by guessing the UUID in the URL.

def _tenant_notification_qs(user):
    """Notifications belonging to this tenant (as recipient)."""
    return Notification.objects.filter(user=user)


def _redirect_to_my_notifications(request):
    """
    Send the user back to ``my-notifications`` while preserving the
    active status filter + page so they land where they were.
    """
    from django.urls import reverse
    params = []
    for key in ("status", "page"):
        value = request.POST.get(f"return_{key}") or request.GET.get(key)
        if value:
            # Constrain to known-safe values before interpolating into
            # the redirect URL — avoids reflecting arbitrary query string
            # data back into the Location header.
            if key == "status" and value not in ("all", "read", "unread"):
                continue
            if key == "page":
                try:
                    int(value)
                except (TypeError, ValueError):
                    continue
            params.append(f"{key}={value}")
    url = reverse("tenant:my-notifications")
    if params:
        return redirect(f"{url}?{'&'.join(params)}")
    return redirect(url)


@login_required
@require_POST
def mark_notification_as_read_view(request, notification_id):
    """
    Mark a single tenant-owned notification as read. Sets ``read_at`` so
    the timestamp is preserved on the row.
    """
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    notification = get_object_or_404(
        _tenant_notification_qs(request.user),
        pk=notification_id,
    )

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at", "updated_at"])
        messages.success(
            request,
            f'Notification "{notification.title}" marked as read.',
        )
    else:
        messages.info(request, "Notification was already marked as read.")

    return _redirect_to_my_notifications(request)


@login_required
@require_POST
def mark_notification_as_unread_view(request, notification_id):
    """Revert a single tenant-owned notification back to the unread state."""
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    notification = get_object_or_404(
        _tenant_notification_qs(request.user),
        pk=notification_id,
    )

    if notification.is_read:
        notification.is_read = False
        notification.read_at = None
        notification.save(update_fields=["is_read", "read_at", "updated_at"])
        messages.success(
            request,
            f'Notification "{notification.title}" marked as unread.',
        )
    else:
        messages.info(request, "Notification was already unread.")

    return _redirect_to_my_notifications(request)


@login_required
@require_POST
def mark_all_notifications_as_read_view(request):
    """Bulk-mark every unread notification belonging to this tenant as read."""
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    qs = _tenant_notification_qs(request.user).filter(is_read=False)
    count = qs.count()
    if count:
        now = timezone.now()
        qs.update(is_read=True, read_at=now, updated_at=now)
        messages.success(
            request,
            f'Marked {count} notification{"s" if count != 1 else ""} as read.',
        )
    else:
        messages.info(request, "No unread notifications to mark.")

    return _redirect_to_my_notifications(request)


@login_required
@require_POST
def delete_notification_view(request, notification_id):
    """Permanently delete a single tenant-owned notification."""
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    notification = get_object_or_404(
        _tenant_notification_qs(request.user),
        pk=notification_id,
    )
    title = notification.title
    notification.delete()
    messages.success(request, f'Notification "{title}" deleted.')

    return _redirect_to_my_notifications(request)


@login_required
@require_POST
def clear_all_notifications_view(request):
    """
    Bulk-delete every notification belonging to this tenant (received).
    Distinct from "delete one" — used when the tenant wants to wipe the
    inbox entirely.
    """
    if not tenant_required(request):
        return render(request, "403.html", status=403)

    qs = _tenant_notification_qs(request.user)
    count = qs.count()
    if count:
        qs.delete()
        messages.success(
            request,
            f'Cleared {count} notification{"s" if count != 1 else ""}.',
        )
    else:
        messages.info(request, "No notifications to clear.")

    return _redirect_to_my_notifications(request)