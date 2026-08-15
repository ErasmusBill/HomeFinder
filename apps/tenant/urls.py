from django.urls import path
from apps.tenant.views import (
    tenant_dashboard_view,
    saved_properties_list_view,
    toggle_saved_property_view,
    property_alerts_list_create_view,
    viewing_requests_list_create_view,
)

app_name = "tenant"

urlpatterns = [
    path("dashboard/", tenant_dashboard_view, name="dashboard"),
    path("saved-properties/", saved_properties_list_view, name="saved_properties_list"),
    path("properties/<uuid:property_id>/toggle-save/", toggle_saved_property_view, name="toggle_save_property"),
    path("alerts/", property_alerts_list_create_view, name="property_alerts"),
    path("viewing-requests/", viewing_requests_list_create_view, name="viewing_requests"),
    path("properties/<uuid:property_id>/request-viewing/", viewing_requests_list_create_view, name="request_viewing"),
]