from django import forms
from django.forms import ModelForm

from apps.Subscription.models import SubscriptionPlan, LandlordSubscription


class LandlordSubscriptionForm(forms.ModelForm):
    """Admin-only: manual correction of a subscription record."""
    class Meta:
        model = LandlordSubscription
        fields = ["landlord", "plan", "start_date", "end_date", "status", "is_active"]