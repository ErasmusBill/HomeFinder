from django import forms

from .models import SubscriptionPlan, LandlordSubscription


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = ["name", "description", "price", "duration_days", "maximum_listings", "is_active"]


class LandlordSubscriptionForm(forms.ModelForm):
    class Meta:
        model = LandlordSubscription
        fields = ["landlord", "plan", "start_date", "end_date", "is_active", "payment_reference"]
        widgets = {
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
