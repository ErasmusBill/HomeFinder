from django.urls import path
from . import views


app_name = 'home_finder'

urlpatterns = [
    path('', views.home, name='home'),
    path('properties/', views.get_all_properties, name='list_properties'),
    path('about/', views.about, name='about'),
    path('how-it-works/', views.how_it_works, name='how_it_works'),
    path('contact/', views.contact, name='contact'),
    path('property/<slug:slug>/', views.get_property_detail, name='property_detail'),
    path('property/<slug:slug>/interest/', views.express_property_interest, name='express_property_interest'),
    path('property/<slug:slug>/book-tour/', views.book_property_tour, name='book_property_tour'),
    path('property/<slug:slug>/book-tour/', views.book_property_tour, name='book_tour'),
    path('api/cascade-locations/', views.cascade_locations, name='cascade_locations'),

    path('api/featured-properties/', views.featured_properties_api, name='featured_properties_api'),
]

