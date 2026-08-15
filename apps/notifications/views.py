from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import NotificationsForm
from .models import Notification


def _is_admin_or_staff(user):
    return user.role == user.Role.ADMIN or user.is_staff or user.is_superuser


def _get_queryset_for(user):
    """
    Admins / staff see every notification; landlords see notifications they
    received and those they sent.
    Returns a queryset, never a list, so callers can keep paginating /
    counting cheaply.
    """
    qs = Notification.objects.select_related('user').order_by('-created_at')
    if _is_admin_or_staff(user):
        return qs
    return qs.filter(Q(user=user) | Q(created_by=user))


def _build_form(request, *args, **kwargs):
    """Construct NotificationsForm with the logged-in user attached."""
    form = NotificationsForm(*args, request_user=request.user, **kwargs)
    form._request_user = request.user
    return form


@login_required
def create_notification(request):
    if request.user.role != request.user.Role.LANDLORD and not _is_admin_or_staff(request.user):
        messages.error(request, "Only registered landlords and administrators can create notifications.")
        return redirect('landloards:landloards_dashboard')

    if request.method == "POST":
        form = _build_form(request, request.POST)
        if form.is_valid():
            notification = form.save(commit=False)
            notification.created_by = request.user
            notification.save()
            messages.success(request, "Notification created successfully.")
            return redirect("notifications:list-notifications")
        else:
            messages.error(request, "Error creating notification. Please check the fields below.")
    else:
        form = _build_form(request)

    return render(request, 'notifications/notification_form.html', {'form': form})


@login_required
def update_notification(request, notification_id):
    if request.user.role != request.user.Role.LANDLORD and not _is_admin_or_staff(request.user):
        messages.error(request, "You are not authorized to perform this action.")
        return redirect("landloards:landloards_dashboard")

    if _is_admin_or_staff(request.user):
        notification = get_object_or_404(Notification, pk=notification_id)
    else:
        notification = get_object_or_404(_get_queryset_for(request.user), pk=notification_id)

    if request.method == "POST":
        form = _build_form(request, request.POST, instance=notification)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.save()
            messages.success(request, "Notification updated successfully.")
            return redirect("notifications:list-notifications")
        else:
            messages.error(request, "An error occurred while updating the notification.")
    else:
        form = _build_form(request, instance=notification)

    return render(request, 'notifications/notification_form.html', {'form': form, 'notification': notification})


@login_required
@require_POST
def delete_notification(request, notification_id):
    if request.user.role != request.user.Role.LANDLORD and not _is_admin_or_staff(request.user):
        messages.error(request, "You are not authorized to perform this action.")
        return _redirect_to_list(request)

    qs = _get_queryset_for(request.user)
    notification = get_object_or_404(qs, pk=notification_id)

    title = notification.title
    notification.delete()
    messages.success(request, f'Notification "{title}" deleted.')
    return _redirect_to_list(request)


@login_required
def list_notifications(request):
    user = request.user

    # Only landlords, admins and staff can see the notifications list.
    # Tenants don't get an inbox page; their notifications are surfaced
    # elsewhere (badge, dropdown, etc.) — change this branch if a tenant
    # inbox is added later.
    if user.role not in (user.Role.ADMIN, user.Role.LANDLORD) and not user.is_staff and not user.is_superuser:
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    qs = _get_queryset_for(user)

    # Read-state filter — `?filter=unread` / `?filter=read` / default `all`.
    # The template uses the same `filter` value to highlight the right tab
    # and to show the empty-state copy for the chosen filter.
    active_filter = request.GET.get('filter', 'all')
    if active_filter not in ('all', 'unread', 'read'):
        active_filter = 'all'
    if active_filter == 'unread':
        qs = qs.filter(is_read=False)
    elif active_filter == 'read':
        qs = qs.filter(is_read=True)

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Counts for the sidebar summary + the tab labels. Computed from the
    # unfiltered, user-scoped queryset so the counts stay consistent
    # regardless of which tab is active.
    base_qs = _get_queryset_for(user)
    unread_count = base_qs.filter(is_read=False).count()
    read_count = base_qs.filter(is_read=True).count()
    total_count = base_qs.count()

    return render(request, 'notifications/notification_list.html', {
        'notifications': page_obj,
        'active_filter': active_filter,
        'unread_count': unread_count,
        'read_count': read_count,
        'total_count': total_count,
    })


# ---------------------------------------------------------------------------
# State-toggle actions
# ---------------------------------------------------------------------------
# All of these are POST-only. GET would let a stray <img src="..."> mark a
# notification as read, which is bad UX (no feedback) and a CSRF footgun.
# We also always re-resolve the notification through the user-scoped
# queryset so a landlord can't toggle someone else's row by guessing a UUID.

def _redirect_to_list(request):
    """Preserve the active filter/page when bouncing back to the list."""
    params = []
    for key in ('filter', 'page'):
        value = request.POST.get(f'return_{key}') or request.GET.get(key)
        if value:
            params.append(f'{key}={value}')
    url = reverse('notifications:list-notifications')
    if params:
        return redirect(f'{url}?{"&".join(params)}')
    return redirect(url)


@login_required
@require_POST
def mark_as_read(request, notification_id):
    qs = _get_queryset_for(request.user)
    notification = get_object_or_404(qs, pk=notification_id)

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at', 'updated_at'])
        messages.success(request, f'Notification "{notification.title}" marked as read.')
    else:
        messages.info(request, 'Notification was already marked as read.')

    return _redirect_to_list(request)


@login_required
@require_POST
def mark_as_unread(request, notification_id):
    qs = _get_queryset_for(request.user)
    notification = get_object_or_404(qs, pk=notification_id)

    if notification.is_read:
        notification.is_read = False
        notification.read_at = None
        notification.save(update_fields=['is_read', 'read_at', 'updated_at'])
        messages.success(request, f'Notification "{notification.title}" marked as unread.')
    else:
        messages.info(request, 'Notification was already unread.')

    return _redirect_to_list(request)


@login_required
@require_POST
def mark_all_as_read(request):
    qs = _get_queryset_for(request.user).filter(is_read=False)
    now = timezone.now()
    # Capture the count before the update so the success message can say
    # "marked 5 notifications as read" rather than a generic sentence.
    count = qs.count()
    if count:
        qs.update(is_read=True, read_at=now, updated_at=now)
        messages.success(request, f'Marked {count} notification{"s" if count != 1 else ""} as read.')
    else:
        messages.info(request, 'No unread notifications to mark.')

    return _redirect_to_list(request)


@login_required
@require_POST
def clear_notifications(request):
    """
    Wipe every notification belonging to the current user (or every
    notification, if the user is admin/staff). Distinct from "delete" —
    the per-row delete handler is still there for the case where a
    landlord wants to remove a single notification they sent to a
    specific user.
    """
    qs = _get_queryset_for(request.user)
    count = qs.count()
    if count:
        qs.delete()
        messages.success(request, f'Cleared {count} notification{"s" if count != 1 else ""}.')
    else:
        messages.info(request, 'No notifications to clear.')

    return _redirect_to_list(request)
