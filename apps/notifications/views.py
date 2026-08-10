from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from .forms import NotificationsForm
from .models import Notification


def _is_admin_or_staff(user):
    return user.role == user.Role.ADMIN or user.is_staff or user.is_superuser


@login_required
def create_notification(request):
    if request.user.role != request.user.Role.LANDLORD and not _is_admin_or_staff(request.user):
        messages.error(request, "Only registered landlords and administrators can create notifications.")
        return redirect('landloards:landloards_dashboard')

    if request.method == "POST":
        form = NotificationsForm(request.POST)
        if form.is_valid():
            notification = form.save(commit=False)

            # If a landlord is creating it, ensure they are set as the sender/owner
            # (or if your system means the notification belongs to the landlord creating it)
            if request.user.role == request.user.Role.LANDLORD and not _is_admin_or_staff(request.user):
                notification.user = request.user  # Or adjust if they are picking a tenant

            notification.save()
            messages.success(request, "Notification created successfully.")
            return redirect("notifications:list-notifications")
        else:
            messages.error(request, "Error creating notification. Please check the fields below.")
    else:
        form = NotificationsForm()

    return render(request, 'notifications/create.html', {'form': form})


@login_required
def update_notification(request, notification_id):
    if request.user.role != request.user.Role.LANDLORD and not _is_admin_or_staff(request.user):
        messages.error(request, "You are not authorized to perform this action.")
        return redirect("landloards:landloards_dashboard")

    # Fetch the notification ensuring landlords can ONLY edit their own
    if _is_admin_or_staff(request.user):
        notification = get_object_or_404(Notification, pk=notification_id)
    else:
        notification = get_object_or_404(Notification, pk=notification_id, user=request.user)

    if request.method == "POST":
        form = NotificationsForm(request.POST, instance=notification)
        if form.is_valid():
            form.save()
            messages.success(request, "Notification updated successfully.")
            return redirect("notifications:list-notifications")
        else:
            messages.error(request, "An error occurred while updating the notification.")
            # Render the form again with errors instead of redirecting away silently
            return render(request, 'notifications/update.html', {'form': form, 'notification': notification})
    else:
        form = NotificationsForm(instance=notification)

    return render(request, 'notifications/update.html', {'form': form, 'notification': notification})


@login_required
def delete_notification(request, notification_id):
    if request.user.role != request.user.Role.LANDLORD and not _is_admin_or_staff(request.user):
        messages.error(request, "You are not authorized to perform this action.")
        return redirect("landloards:landloards_dashboard")

    # Fetch the notification ensuring landlords can ONLY delete their own
    if _is_admin_or_staff(request.user):
        notification = get_object_or_404(Notification, pk=notification_id)
    else:
        notification = get_object_or_404(Notification, pk=notification_id, user=request.user)

    notification.delete()
    messages.success(request, "Notification deleted successfully.")
    return redirect("notifications:list-notifications")


@login_required
def list_notifications(request):
    user = request.user

    if not user.is_authenticated or user.role not in [user.Role.ADMIN, user.Role.LANDLORD, "admin", "landlord"] and not user.is_staff:
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    if user.role == user.Role.ADMIN or user.is_staff or getattr(user, "is_superuser", False):
        notifications = Notification.objects.select_related('user').order_by('-created_at')
    else:
        notifications = Notification.objects.filter(user=user).select_related('user').order_by('-created_at')

    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'notifications/notification_list.html', {
        'notifications': page_obj,
    })