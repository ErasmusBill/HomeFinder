from django.urls import path
from . import views


app_name = 'home_finder'

urlpatterns = [
    path('', views.home, name='home'),
    path('properties/', views.get_all_properties, name='list_properties'),
    path('property/<slug:slug>/', views.get_property_detail, name='property_detail'),
]