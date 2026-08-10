from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('list-notification/', views.list_notifications, name='list-notifications'),
    path('create/', views.create_notification, name='create-notification'),
    path('<str:notification_id>/update/', views.update_notification, name='update-notification'),
    path('<str:notification_id>/delete/', views.delete_notification, name='delete-notification'),
]