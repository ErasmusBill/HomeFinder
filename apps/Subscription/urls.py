from django.urls import path
from . import views

app_name = "subscription"

urlpatterns = [


    # Payment initiation & confirmation
    path('plans/<uuid:plan_id>/subscribe/', views.initiate_subscription_payment, name='initiate_payment'),
    path('callback/', views.paystack_callback, name='paystack_callback'),
    path('webhook/', views.paystack_webhook, name='paystack_webhook'),

    # Cancel / reactivate
    path('cancel/', views.cancel_subscription_view, name='cancel'),
    path('reactivate/', views.reactivate_subscription_view, name='reactivate'),

    # plan
    path('subscriptions/', views.list_all_subscription, name='plans'),
    path('plans/<uuid:plan_id>/change/', views.change_plan_view, name='change_plan'),

]