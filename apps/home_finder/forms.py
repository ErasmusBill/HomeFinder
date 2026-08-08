from django import forms
from apps.home_finder.models import Amenity, Property, PropertyMedia, LandlordDocument

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


class LandlordDocumentForm(TailwindModelForm):
    """
    Landlord-facing upload form. Deliberately excludes 'landlord',
    'verification_status', 'rejection_reason', 'reviewed_by', and
    'reviewed_at' — those are set by the view (landlord = request.user)
    or by staff during review, never by the uploader directly.
    """
    class Meta:
        model = LandlordDocument
        fields = [
            "document_type",
            "property",
            "file",
            "expires_at",
        ]

    def __init__(self, *args, landlord=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Only let a landlord attach a document to one of their own
        # properties, not any property in the system.
        if landlord is not None:
            self.fields["property"].queryset = Property.objects.filter(landlord=landlord)
        self.fields["property"].required = False


class LandlordDocumentReviewForm(TailwindModelForm):
    """
    Staff-facing review form — used in an admin/verification view to
    approve or reject an uploaded document, separate from the upload
    form so a landlord can never set their own verification_status.
    """
    class Meta:
        model = LandlordDocument
        fields = [
            "verification_status",
            "rejection_reason",
        ]