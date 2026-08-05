from django.urls import path
from . import views

app_name = 'landlords'

urlpatterns = [
    path('landlord_dashboard', views.landlords_dashboard, name='landlords_dashboard'),
    path('amenities/', views.list_amenities, name='amenity_list'),
    path('amenities/create/', views.create_amenity, name='create_amenity'),
    path('amenities/<str:amenity_id>/update/', views.update_amenity, name='update_amenity'),
    path('amenities/<str:amenity_id>/delete/', views.delete_amenity, name='delete_amenity'),

    path('properties/', views.list_properties, name='property_list'),
    path('properties/create/', views.create_property, name='create_property'),
    path('properties/<slug:slug>/', views.property_detail, name='property_detail'),
    path('properties/<str:property_id>/update/', views.update_property, name='update_property'),
    path('properties/<str:property_id>/delete/', views.delete_property, name='delete_property'),
    path('properties/<str:property_id>/verify/', views.verify_property, name='verify_property'),

    path('properties/<str:property_id>/media/add/', views.add_property_media, name='add_property_media'),
    path('properties/media/<str:media_id>/delete/', views.delete_property_media, name='delete_property_media'),

    path('subscription/list_landlord_subscription/',views.list_landlord_subscription, name='list_landlord_subscription'),
]
