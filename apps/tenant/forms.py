from django import forms
from django.utils import timezone

from apps.tenant.models import PropertyAlert, ViewingRequest

INPUT_CLASS = "w-full px-4 py-2.5 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
SELECT_CLASS = "w-full px-4 py-2.5 border border-gray-300 rounded-lg bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
TEXTAREA_CLASS = "w-full px-4 py-2.5 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition resize-none"

class PropertyAlertForm(forms.ModelForm):
    class Meta:
        model = PropertyAlert
        fields = ["region", "district", "area", "min_price", "max_price", "room_type"]
        labels = {
            "region": "Region",
            "district": "District",
            "area": "Area",
            "min_price": "Minimum Price",
            "max_price": "Maximum Price",
            "room_type": "Room Type",
        }
        widgets = {
            "region": forms.Select(attrs={"class": SELECT_CLASS}),
            "district": forms.Select(attrs={"class": SELECT_CLASS}),
            "area": forms.Select(attrs={"class": SELECT_CLASS}),
            "min_price": forms.NumberInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. 500", "min": "0", "step": "0.01"}),
            "max_price": forms.NumberInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. 2000", "min": "0", "step": "0.01"}),
            "room_type": forms.Select(attrs={"class": SELECT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["district"].required = False
        self.fields["area"].required = False
        self.fields["region"].empty_label = "Select region"
        self.fields["district"].empty_label = "Select district"
        self.fields["area"].empty_label = "Select area"
        self.fields["room_type"].empty_label = "Select room type"

    def clean_min_price(self):
        min_price = self.cleaned_data.get("min_price")
        if min_price is not None and min_price < 0:
            raise forms.ValidationError("Minimum price cannot be negative.")
        return min_price

    def clean_max_price(self):
        max_price = self.cleaned_data.get("max_price")
        if max_price is not None and max_price < 0:
            raise forms.ValidationError("Maximum price cannot be negative.")
        return max_price

    def clean(self):
        cleaned_data = super().clean()
        min_price = cleaned_data.get("min_price")
        max_price = cleaned_data.get("max_price")
        if min_price is not None and max_price is not None and min_price > max_price:
            self.add_error("max_price", "Maximum price must be greater than or equal to minimum price.")
        return cleaned_data



class ViewingRequestForm(forms.ModelForm):
    class Meta:
        model = ViewingRequest
        fields = ["property", "preferred_date", "preferred_time", "notes"]
        labels = {
            "property": "Select Property",
            "preferred_date": "Preferred Date",
            "preferred_time": "Preferred Time",
            "notes": "Additional Notes",
        }
        widgets = {
            "property": forms.Select(attrs={"class": SELECT_CLASS}),
            "preferred_date": forms.DateInput(attrs={"type": "date", "class": INPUT_CLASS}),
            "preferred_time": forms.TimeInput(attrs={"type": "time", "class": INPUT_CLASS}),
            "notes": forms.Textarea(attrs={"rows": 4, "class": TEXTAREA_CLASS, "placeholder": "Any specific notes for the landlord..."}),
        }

    def __init__(self, *args, exclude_property=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notes"].required = False
        today = timezone.localdate()
        self.fields["preferred_date"].widget.attrs.update({"min": today.isoformat()})

        if exclude_property:
            self.fields.pop("property", None)
            return

        from apps.home_finder.models import Property

        base_qs = Property.objects.filter(
            is_available=True,
        ).select_related("region", "district", "area").order_by("-created_at")

        bound_property = self.data.get(self.add_prefix("property")) if self.is_bound else None
        if bound_property:
            base_qs = base_qs | Property.objects.filter(pk=bound_property)
        self.fields["property"].queryset = base_qs.distinct()

    def clean_preferred_date(self):
        preferred_date = self.cleaned_data.get("preferred_date")
        if preferred_date and preferred_date < timezone.localdate():
            raise forms.ValidationError("Viewing date cannot be in the past.")
        return preferred_date

    def clean(self):
        cleaned_data = super().clean()
        preferred_date = cleaned_data.get("preferred_date")
        preferred_time = cleaned_data.get("preferred_time")
        today = timezone.localdate()
        current_time = timezone.localtime().time()
        if preferred_date == today and preferred_time and preferred_time <= current_time:
            self.add_error("preferred_time", "Please select a future time for today's viewing.")
        return cleaned_data