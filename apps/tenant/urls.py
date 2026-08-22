from django.urls import path
from apps.tenant import views

app_name = "tenant"

urlpatterns = [
    path("dashboard/", views.tenant_dashboard_view, name="dashboard"),
    path("saved-properties/", views.saved_properties_list_view, name="saved_properties_list"),
    path("saved-properties/clear/", views.clear_saved_properties_view, name="clear_saved_properties"),
    path("properties/<uuid:property_id>/toggle-save/", views.toggle_saved_property_view, name="toggle_save_property"),
    path("property-views/", views.property_views_list_view, name="property_views"),
    path("property-views/clear/", views.clear_property_views_view, name="clear_property_views"),
    path("properties/<uuid:property_id>/", views.tenant_property_detail_view, name="property_detail"),
    path("alerts/", views.property_alerts_list_create_view, name="property_alerts"),
    path("alerts/<uuid:alert_id>/update/", views.update_property_alert_view, name="update_property_alert"),
    path("alerts/<uuid:alert_id>/delete/", views.delete_property_alert_view, name="delete_property_alert"),
    path("alerts/<uuid:alert_id>/toggle/", views.toggle_property_alert_view, name="toggle_property_alert"),
    path("viewing-requests/", views.viewing_requests_list_create_view, name="viewing_requests"),
    path("properties/<uuid:property_id>/request-viewing/", views.viewing_requests_list_create_view, name="request_viewing"),
    path("viewing-requests/<uuid:request_id>/cancel/", views.cancel_viewing_request_view, name="cancel_viewing_request"),
    path("viewing-requests/<uuid:request_id>/update/", views.update_viewing_request_view, name="update_viewing_request"),
    path("viewing-requests/<uuid:request_id>/delete/", views.delete_viewing_request_view, name="delete_viewing_request"),
    path("viewing-requests/<uuid:request_id>/", views.viewing_request_detail_view, name="viewing_request_detail"),

    path('tenant/<int:tenant_pk>/notifications/', views.tenant_notifications_detail_view, name='tenant-notifications'),

    # Tenant viewing their own notifications
    path('my-notifications/', views.my_tenant_notifications_view, name='my-notifications'),

    # ------------------------------------------------------------------ #
    # Tenant notification actions (all POST only)                       #
    # ------------------------------------------------------------------ #
    # Per-row actions
    path('notifications/<uuid:notification_id>/mark-read/', views.mark_notification_as_read_view, name='mark_notification_read'),
    path('notifications/<uuid:notification_id>/mark-unread/', views.mark_notification_as_unread_view, name='mark_notification_unread'),
    path('notifications/<uuid:notification_id>/delete/', views.delete_notification_view, name='delete_notification'),
    # Bulk actions
    path('notifications/mark-all-read/', views.mark_all_notifications_as_read_view, name='mark_all_notifications_read'),
    path('notifications/clear-all/', views.clear_all_notifications_view, name='clear_all_notifications'),
]