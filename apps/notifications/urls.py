from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('list-notification/', views.list_notifications, name='list-notifications'),
    path('create/', views.create_notification, name='create-notification'),
    path('<uuid:notification_id>/update/', views.update_notification, name='update-notification'),
    path('<uuid:notification_id>/delete/', views.delete_notification, name='delete-notification'),
    # State toggles (POST only — mutating actions)
    path('<uuid:notification_id>/mark-read/', views.mark_as_read, name='mark-read'),
    path('<uuid:notification_id>/mark-unread/', views.mark_as_unread, name='mark-unread'),
    # Bulk actions
    path('mark-all-read/', views.mark_all_as_read, name='mark-all-read'),
    path('clear-all/', views.clear_notifications, name='clear-all'),
]