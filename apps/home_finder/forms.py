from django import forms
from apps.home_finder.models import Amenity, Property, PropertyMedia


INPUT_CLASSES = (
    "block w-full rounded-lg border border-gray-300 "
    "bg-white px-4 py-3 text-sm "
    "focus:border-green-600 focus:ring-2 "
    "focus:ring-green-500/20 focus:outline-none"
)

SELECT_CLASSES = INPUT_CLASSES

TEXTAREA_CLASSES = (
    "block w-full rounded-lg border border-gray-300 "
    "bg-white px-4 py-3 text-sm "
    "focus:border-green-600 focus:ring-2 "
    "focus:ring-green-500/20 focus:outline-none"
)

CHECKBOX_CLASSES = (
    "h-5 w-5 rounded border-gray-300 "
    "text-green-600 focus:ring-green-500"
)


class TailwindModelForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():

            if isinstance(field.widget, forms.TextInput):
                field.widget.attrs["class"] = INPUT_CLASSES

            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs["class"] = INPUT_CLASSES

            elif isinstance(field.widget, forms.DateInput):
                field.widget.attrs.update({
                    "class": INPUT_CLASSES,
                    "type": "date",
                })

            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = SELECT_CLASSES

            elif isinstance(field.widget, forms.SelectMultiple):
                field.widget.attrs["class"] = SELECT_CLASSES

            elif isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs["class"] = INPUT_CLASSES

            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs["class"] = TEXTAREA_CLASSES

            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = CHECKBOX_CLASSES


class AmenityForm(TailwindModelForm):

    class Meta:
        model = Amenity
        fields = [
            "name",
            "description",
        ]


class PropertyCreateForm(TailwindModelForm):

    class Meta:
        model = Property

        fields = [
            "title",
            "description",
            "cover_image",

            "price",
            "payment_period",

            "room_type",

            "region",
            "district",
            "town",
            "area",

            "amenities",

            "bedrooms",
            "bathrooms",
            "toilets",
            "parking_spaces",
            "floor_area",

            "is_furnished",
            "is_available",
            "available_from",
        ]

        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                }
            ),
        }


class PropertyUpdateForm(TailwindModelForm):

    class Meta:
        model = Property

        fields = [
            "title",
            "description",
            "cover_image",

            "price",
            "payment_period",

            "room_type",

            "region",
            "district",
            "town",
            "area",

            "amenities",

            "bedrooms",
            "bathrooms",
            "toilets",
            "parking_spaces",
            "floor_area",

            "is_furnished",
            "is_available",
            "available_from",
        ]

        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                }
            ),
        }


class PropertyVerificationForm(TailwindModelForm):

    class Meta:
        model = Property

        fields = [
            "verification_status",
        ]


class PropertyMediaForm(TailwindModelForm):

    class Meta:
        model = PropertyMedia

        # 'property' can be excluded if you handle assignment via URL kwargs in your view.
        fields = [
            "file",
            "media_type",
            "caption",
            "order",
            "is_public",
        ]