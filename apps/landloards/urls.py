from django.urls import path
from . import views, views_onboarding

app_name = 'landloards'

urlpatterns = [
    # Onboarding
    path('onboarding/profile/', views_onboarding.onboarding_profile, name='onboarding_profile'),
    path('onboarding/pricing/', views_onboarding.onboarding_pricing, name='onboarding_pricing'),
    path('onboarding/start-trial/', views_onboarding.start_free_trial, name='start_free_trial'),
    path('landlord_dashboard', views.landlords_dashboard, name='landloards_dashboard'),
    path('landlord_dashboard/', views.landlords_dashboard, name='landloards_dashboard_slash'),
    path('dashboard/', views.landlords_dashboard, name='dashboard'),

    # Amenities
    path('amenities/', views.list_amenities, name='amenity_list'),
    path('amenities/create/', views.create_amenity, name='create_amenity'),
    path('amenities/<str:amenity_id>/update/', views.update_amenity, name='update_amenity'),
    path('amenities/<str:amenity_id>/delete/', views.delete_amenity, name='delete_amenity'),

    # Properties
    path('properties/', views.list_properties, name='property_list'),
    path('properties/create/', views.create_property, name='create_property'),
    path('properties/<slug:slug>/', views.property_detail, name='property_detail'),
    path('properties/<str:property_id>/update/', views.update_property, name='update_property'),
    path('properties/<str:property_id>/delete/', views.delete_property, name='delete_property'),
    path('properties/<str:property_id>/verify/', views.verify_property, name='verify_property'),
    path('properties/<str:property_id>/media/add/', views.add_property_media, name='add_property_media'),
    path('properties/media/<str:media_id>/delete/', views.delete_property_media, name='delete_property_media'),

    # Landlord documents
    path('documents/', views.list_landlord_documents, name='landlord_document_list'),
    path('documents/create/', views.create_landlord_document, name='create_landlord_document'),
    path('documents/<str:document_id>/update/', views.update_landlord_document, name='update_landlord_document'),
    path('documents/<str:document_id>/delete/', views.delete_landlord_document, name='delete_landlord_document'),
    path('documents/<str:document_id>/review/', views.review_landlord_document, name='review_landlord_document'),

    # Subscription
    path('subcription/list_landlord_subscription/', views.list_landlord_subscription, name='list_landlord_subscription'),
    path('plans/<uuid:plan_id>/confirm/', views.confirm_plan_change_view, name='confirm_plan_change'),

    # Viewing requests (landlord inbox)
    path('viewing-requests/', views.viewing_requests_list_view, name='viewing_requests'),
    path('viewing-requests/<uuid:request_id>/', views.viewing_request_detail_view, name='viewing_request_detail'),
    path('viewing-requests/<uuid:request_id>/confirm/', views.confirm_viewing_request_view, name='confirm_viewing_request'),
    path('viewing-requests/<uuid:request_id>/decline/', views.decline_viewing_request_view, name='decline_viewing_request'),
    path('viewing-requests/<uuid:request_id>/reschedule/', views.reschedule_viewing_request_view, name='reschedule_viewing_request'),
    path('viewing-requests/<uuid:request_id>/complete/', views.mark_viewing_completed_view, name='complete_viewing_request'),
]