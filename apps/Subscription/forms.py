from django import forms
from django.forms import ModelForm

from apps.Subscription.models import SubscriptionPlan, LandlordSubscription


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = ["name", "description", "price", "durations_days", "maximum_listings", "is_active"]


class LandlordSubscriptionForm(forms.ModelForm):
    class Meta:
        model = LandlordSubscription
        fields = ["landlord", "plan", "start_date", "end_date", "is_active"]