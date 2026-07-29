from django.urls import path
from .views import (
    create_region,
    update_region,
    delete_region,
    add_district,
    update_district,
    add_town,
    update_town,
    add_area,
    update_area,
    list_locations,
)

app_name = "locations"

urlpatterns = [
    path("", list_locations, name="list_locations"),
    path("regions/create/", create_region, name="create_region"),
    path("regions/<str:region_id>/update/", update_region, name="update_region"),
    path("regions/<str:region_id>/delete/", delete_region, name="delete_region"),
    path("districts/add/", add_district, name="add_district"),
    path("districts/<str:district_id>/update/", update_district, name="update_district"),
    path("towns/add/", add_town, name="add_town"),
    path("towns/<str:town_id>/update/", update_town, name="update_town"),
    path("areas/add/", add_area, name="add_area"),
    path("areas/<str:area_id>/update/", update_area, name="update_area"),
]