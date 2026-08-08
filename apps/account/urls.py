from django.urls import path
from . import views

app_name = 'account'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('profile/update/', views.update_profile_view, name='update_profile'),
    path('password/forgot/', views.forgot_password_view, name='forgot_password'),
    path('password/reset/', views.reset_password_confirm_view, name='reset_password_confirm'),
    path('password/change/', views.change_password_view, name='change_password'),
]