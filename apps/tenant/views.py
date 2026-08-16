from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.account.models import User
from apps.home_finder.models import Property
from apps.notifications.models import Notification
from apps.tenant.forms import PropertyAlertForm, ViewingRequestForm
from apps.tenant.models import PropertyAlert, PropertyView, SavedProperty, ViewingRequest
from apps.tenant.selectors import get_tenant_saved_properties, get_tenant_property_views, get_tenant_property_alerts, get_tenant_viewing_requests

def tenant_required(request):
    return request.user.is_authenticated and (request.user.role == request.user.Role.TENANT)

def tenant_forbidden():
    return render(request=None, template_name="403.html", status=403)

def record_property_view(tenant, property_obj):
    PropertyView.objects.update_or_create(tenant=tenant, property=property_obj, defaults={})

@login_required
def tenant_dashboard_view(request):
    if not tenant_required(request): return render(request, "403.html", status=403)
    tenant = request.user

    saved_properties = get_tenant_saved_properties(tenant)
    property_views = get_tenant_property_views(tenant)
    property_alerts = get_tenant_property_alerts(tenant)
    viewing_requests = get_tenant_viewing_requests(tenant)

    recommended_properties = Property.objects.filter(is_available=True).select_related("region", "district", "area").prefetch_related("media").order_by("-created_at")[:6]

    upcoming_viewings = [viewing for viewing in viewing_requests if viewing.status in [ViewingRequest.Status.PENDING, ViewingRequest.Status.CONFIRMED]][:3]

    context = {"saved_count": len(saved_properties), "views_count": len(property_views), "alerts_count": len(property_alerts), "requests_count": len(viewing_requests), "saved_properties": saved_properties[:4], "property_views": property_views[:4], "property_alerts": property_alerts[:3], "upcoming_viewings": upcoming_viewings, "recommended_properties": recommended_properties}
    return render(request, "tenant/dashboard.html", context)

@login_required
def saved_properties_list_view(request):
    if not tenant_required(request): return render(request, "403.html", status=403)
    saved_properties = get_tenant_saved_properties(request.user)

    context = {"saved_properties": saved_properties, "saved_count": len(saved_properties)}
    return render(request, "tenant/saved_properties.html", context)

@login_required
@require_POST
def toggle_saved_property_view(request, property_id):

    if not tenant_required(request): return render(request, "403.html", status=403)
    property_obj = get_object_or_404(Property, pk=property_id)
    saved_property = SavedProperty.objects.filter(tenant=request.user, property=property_obj).first()
    if saved_property: saved_property.delete()
    else: SavedProperty.objects.create(tenant=request.user, property=property_obj)
    return redirect(request.META.get("HTTP_REFERER", "tenant:dashboard"))

@login_required
def property_views_list_view(request):
    if not tenant_required(request): return render(request, "403.html", status=403)
    property_views = get_tenant_property_views(request.user)
    context = {"property_views": property_views, "views_count": len(property_views)}
    return render(request, "tenant/property_views.html", context)

@login_required
@require_POST
def clear_property_views_view(request):
    if not tenant_required(request): return render(request, "403.html", status=403)
    PropertyView.objects.filter(tenant=request.user).delete()
    return redirect("tenant:property_views")

@login_required
def tenant_property_detail_view(request, property_id):
    if not tenant_required(request): return render(request, "403.html", status=403)
    property_obj = get_object_or_404(Property.objects.select_related("region", "district", "area").prefetch_related("media"), pk=property_id)
    record_property_view(tenant=request.user, property_obj=property_obj)
    is_saved = SavedProperty.objects.filter(tenant=request.user, property=property_obj).exists()
    viewing_requests = ViewingRequest.objects.filter(tenant=request.user, property=property_obj).order_by("-preferred_date", "-preferred_time")
    context = {"property": property_obj, "is_saved": is_saved, "viewing_requests": viewing_requests}
    return render(request, "home_finder/property_detail.html", context)

@login_required
def property_alerts_list_create_view(request):
    if not tenant_required(request): return render(request, "403.html", status=403)
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
    context = {"form": form, "alerts": alerts, "alerts_count": len(alerts)}
    return render(request, "tenant/property_alerts.html", context)

@login_required
def update_property_alert_view(request, alert_id):
    if not tenant_required(request): return render(request, "403.html", status=403)
    alert = get_object_or_404(PropertyAlert, pk=alert_id, tenant=request.user)
    if request.method == "POST":
        form = PropertyAlertForm(request.POST, instance=alert)
        if form.is_valid():
            updated_alert = form.save(commit=False)
            updated_alert.tenant = request.user
            updated_alert.save()
            return redirect("tenant:property_alerts")
    else:
        form = PropertyAlertForm(instance=alert)
    context = {"form": form, "alert": alert, "is_update": True}
    return render(request, "tenant/property_alert_form.html", context)

@login_required
@require_POST
def delete_property_alert_view(request, alert_id):
    if not tenant_required(request): return render(request, "403.html", status=403)
    alert = get_object_or_404(PropertyAlert, pk=alert_id, tenant=request.user)
    alert.delete()
    return redirect("tenant:property_alerts")

@login_required
@require_POST
def toggle_property_alert_view(request, alert_id):
    if not tenant_required(request): return render(request, "403.html", status=403)
    alert = get_object_or_404(PropertyAlert, pk=alert_id, tenant=request.user)
    alert.is_active = not alert.is_active
    alert.save(update_fields=["is_active"])
    return redirect("tenant:property_alerts")

@login_required
def viewing_requests_list_create_view(request, property_id=None):
    if not tenant_required(request): return render(request, "403.html", status=403)
    property_obj = None
    if property_id:
        property_obj = get_object_or_404(Property, pk=property_id)
    if request.method == "POST":
        if not property_obj: return render(request, "403.html", status=403)
        form = ViewingRequestForm(request.POST)
        if form.is_valid():
            viewing_request = form.save(commit=False)
            viewing_request.tenant = request.user
            viewing_request.property = property_obj
            viewing_request.save()
            return redirect("tenant:viewing_requests")
    else:
        form = ViewingRequestForm()
    viewing_requests = get_tenant_viewing_requests(request.user)
    context = {"form": form, "property": property_obj, "viewing_requests": viewing_requests}
    return render(request, "tenant/viewing_requests.html", context)

@login_required
@require_POST
def cancel_viewing_request_view(request, request_id):
    if not tenant_required(request): return render(request, "403.html", status=403)
    viewing_request = get_object_or_404(ViewingRequest, pk=request_id, tenant=request.user)
    allowed_statuses = [ViewingRequest.Status.PENDING, ViewingRequest.Status.CONFIRMED]
    if viewing_request.status in allowed_statuses:
        viewing_request.status = ViewingRequest.Status.CANCELLED
        viewing_request.save(update_fields=["status"])
    return redirect("tenant:viewing_requests")

@login_required
def viewing_request_detail_view(request, request_id):
    if not tenant_required(request): return render(request, "403.html", status=403)
    viewing_request = get_object_or_404(ViewingRequest.objects.select_related("property", "property__region", "property__district", "property__area"), pk=request_id, tenant=request.user)
    context = {"viewing_request": viewing_request}
    return render(request, "tenant/viewing_request_detail.html", context)


@login_required
def tenant_notifications_detail_view(request, user_id):
    """
    Full-stack view for an admin or landlord to view all notifications
    related to a specific tenant (by recipient, sender, or GFK target).
    """
    tenant = get_object_or_404(User, pk=user_id)

    # Fetch notification logic
    tenant_type = ContentType.objects.get_for_model(tenant)
    user = getattr(tenant, 'user', tenant)

    notifications = Notification.objects.filter(
        Q(user=user) |
        Q(created_by=user) |
        Q(content_type=tenant_type, object_id=str(tenant.pk))
    ).select_related('user', 'created_by').distinct()

    context = {
        'tenant': tenant,
        'notifications': notifications,
    }

    return render(request, 'tenant/tenant_notifications_list.html', context)


@login_required
def my_tenant_notifications_view(request):
    """
    Full-stack view for a logged-in tenant to see their own related notifications.
    """
    current_user = request.user

    # Optional: If you want to link it to a Tenant profile model associated with the user
    # tenant = Tenant.objects.filter(user=current_user).first()
    # tenant_type = ContentType.objects.get_for_model(tenant) if tenant else None

    notifications = Notification.objects.filter(
        Q(user=current_user) | Q(created_by=current_user)
    ).select_related('user', 'created_by').distinct()

    context = {
        'notifications': notifications,
    }

    return render(request, 'tenant/my_notifications.html', context)