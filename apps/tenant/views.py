from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.home_finder.models import Property
from apps.tenant.forms import PropertyAlertForm, ViewingRequestForm
from apps.tenant.models import SavedProperty, PropertyAlert, ViewingRequest
from apps.tenant.selectors import (
    get_tenant_saved_properties,
    get_tenant_property_views,
    get_tenant_property_alerts,
    get_tenant_viewing_requests,
)


@login_required
def tenant_dashboard_view(request):
    """Renders the main clean tenant dashboard home with top cards and sidebar components."""
    if request.user.role != request.user.Role.TENANT:
        return render(request, "403.html", status=403)

    tenant = request.user

    saved_properties = get_tenant_saved_properties(tenant)
    property_views = get_tenant_property_views(tenant)
    property_alerts = get_tenant_property_alerts(tenant)
    viewing_requests = get_tenant_viewing_requests(tenant)

    # General recommended properties fallback from home finder
    recommended_properties = Property.objects.filter(is_available=True)[:6]

    context = {
        "saved_count": len(saved_properties),
        "views_count": len(property_views),
        "alerts_count": len(property_alerts),
        "requests_count": len(viewing_requests),
        "saved_properties": saved_properties[:4],  # Preview slice for dashboard
        "property_views": property_views[:4],
        "property_alerts": property_alerts[:3],
        "upcoming_viewings": [vr for vr in viewing_requests if vr.status in ['pending', 'confirmed']][:3],
        "recommended_properties": recommended_properties,
    }
    return render(request, "tenant/dashboard.html", context)


@login_required
def saved_properties_list_view(request):
    """Full list of saved properties."""
    if request.user.role != request.user.Role.TENANT:
        return render(request, "403.html", status=403)

    saved_properties = get_tenant_saved_properties(request.user)
    return render(request, "tenant/saved_properties.html", {"saved_properties": saved_properties})


@login_required
@require_POST
def toggle_saved_property_view(request, property_id):
    """Toggles save/unsave state via standard form POST and redirects back."""
    if request.user.role != request.user.Role.TENANT:
        return render(request, "403.html", status=403)

    property_obj = get_object_or_404(Property, id=property_id)
    saved_obj = SavedProperty.objects.filter(tenant=request.user, property=property_obj).first()

    if saved_obj:
        saved_obj.delete()
    else:
        SavedProperty.objects.create(tenant=request.user, property=property_obj)

    return redirect(request.META.get("HTTP_REFERER", "tenant:dashboard"))


@login_required
def property_alerts_list_create_view(request):
    """Lists active alerts and handles creation of new property alerts."""
    if request.user.role != request.user.Role.TENANT:
        return render(request, "403.html", status=403)

    if request.method == "POST":
        form = PropertyAlertForm(request.POST)
        if form.is_valid():
            alert = form.save(commit=False)
            alert.tenant = request.user
            alert.save()
            return redirect("tenant:property_alerts")
    else:
        form = PropertyAlertForm()

    alerts = get_tenant_property_alerts(request.user)
    return render(request, "tenant/property_alerts.html", {"form": form, "alerts": alerts})


@login_required
def viewing_requests_list_create_view(request, property_id=None):
    """Lists viewing requests and handles scheduling a viewing for a specific property."""
    if request.user.role != request.user.Role.TENANT:
        return render(request, "403.html", status=403)

    property_obj = get_object_or_404(Property, id=property_id) if property_id else None

    if request.method == "POST":
        form = ViewingRequestForm(request.POST)
        if form.is_valid() and property_obj:
            viewing_request = form.save(commit=False)
            viewing_request.tenant = request.user
            viewing_request.property = property_obj
            viewing_request.save()
            return redirect("tenant:viewing_requests")
    else:
        form = ViewingRequestForm()

    requests = get_tenant_viewing_requests(request.user)
    context = {
        "form": form,
        "property": property_obj,
        "viewing_requests": requests,
    }
    return render(request, "tenant/viewing_requests.html", context)