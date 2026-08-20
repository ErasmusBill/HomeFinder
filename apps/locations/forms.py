from django import forms

from apps.locations.models import Area, District, Region, Town

TAILWIND_INPUT_CLASSES = (
    "block w-full rounded-xl border border-gray-300 "
    "bg-white px-4 py-3 text-sm text-gray-900 "
    "placeholder:text-gray-400 "
    "focus:border-green-600 focus:outline-none focus:ring-2 focus:ring-green-500/20 "
    "disabled:bg-gray-100 disabled:cursor-not-allowed"
)


class BaseLocationForm(forms.ModelForm):
    placeholder = "Enter name"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "name" in self.fields:
            self.fields["name"].widget.attrs.update(
                {
                    "class": TAILWIND_INPUT_CLASSES,
                    "placeholder": self.placeholder,
                    "autocomplete": "off",
                }
            )

        # Apply Tailwind classes to foreign key dropdowns if they exist in the form
        for field_name in ["region", "district", "town"]:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update(
                    {
                        "class": TAILWIND_INPUT_CLASSES,
                    }
                )
                self.fields[field_name].empty_label = f"Select {field_name.capitalize()}..."


class RegionForm(BaseLocationForm):
    placeholder = "Enter region name"

    class Meta:
        model = Region
        fields = ("name",)


class DistrictForm(BaseLocationForm):
    placeholder = "Enter district name"

    class Meta:
        model = District
        fields = ("region", "name",)


class TownForm(BaseLocationForm):
    placeholder = "Enter town name"

    class Meta:
        model = Town
        fields = ("district", "name",)


class AreaForm(BaseLocationForm):
    placeholder = "Enter area or suburb name"

    class Meta:
        model = Area
        fields = ("town", "name",)


class LocationHierarchyForm(forms.Form):
    region_name = forms.CharField(
        max_length=150,
        label="Region Name",
        widget=forms.TextInput(attrs={
            "class": TAILWIND_INPUT_CLASSES,
            "placeholder": "e.g., Greater Accra, Ashanti",
            "autocomplete": "off",
        })
    )
    district_name = forms.CharField(
        max_length=150,
        required=False,
        label="District Name",
        widget=forms.TextInput(attrs={
            "class": TAILWIND_INPUT_CLASSES,
            "placeholder": "e.g., Accra Metropolitan, Kumasi Metropolitan",
            "autocomplete": "off",
        })
    )
    town_name = forms.CharField(
        max_length=150,
        required=False,
        label="Town Name",
        widget=forms.TextInput(attrs={
            "class": TAILWIND_INPUT_CLASSES,
            "placeholder": "e.g., Accra, Tema, Kumasi",
            "autocomplete": "off",
        })
    )
    area_name = forms.CharField(
        max_length=150,
        required=False,
        label="Area Name",
        widget=forms.TextInput(attrs={
            "class": TAILWIND_INPUT_CLASSES,
            "placeholder": "e.g., Osu, East Legon, Bantama",
            "autocomplete": "off",
        })
    )