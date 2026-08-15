from django import forms
from apps.tenant.models import PropertyAlert, ViewingRequest


class PropertyAlertForm(forms.ModelForm):
    class Meta:
        model = PropertyAlert
        fields = ["region", "district", "area", "min_price", "max_price", "room_type"]
        widgets = {
            "region": forms.Select(attrs={"class": "w-full px-4 py-2 border border-gray-300 rounded-lg"}),
            "district": forms.Select(attrs={"class": "w-full px-4 py-2 border border-gray-300 rounded-lg"}),
            "area": forms.Select(attrs={"class": "w-full px-4 py-2 border border-gray-300 rounded-lg"}),
            "min_price": forms.NumberInput(attrs={"class": "w-full px-4 py-2 border border-gray-300 rounded-lg", "placeholder": "Min Price"}),
            "max_price": forms.NumberInput(attrs={"class": "w-full px-4 py-2 border border-gray-300 rounded-lg", "placeholder": "Max Price"}),
            "room_type": forms.Select(attrs={"class": "w-full px-4 py-2 border border-gray-300 rounded-lg"}),
        }


class ViewingRequestForm(forms.ModelForm):
    class Meta:
        model = ViewingRequest
        fields = ["preferred_date", "preferred_time", "notes"]
        widgets = {
            "preferred_date": forms.DateInput(attrs={"type": "date", "class": "w-full px-4 py-2 border border-gray-300 rounded-lg"}),
            "preferred_time": forms.TimeInput(attrs={"type": "time", "class": "w-full px-4 py-2 border border-gray-300 rounded-lg"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "w-full px-4 py-2 border border-gray-300 rounded-lg", "placeholder": "Any specific notes for the landlord..."}),
        }