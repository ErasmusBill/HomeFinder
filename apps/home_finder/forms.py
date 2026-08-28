from django import forms
from django.utils import timezone
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
            # NOTE: order matters here. DateInput/TimeInput/DateTimeInput all
            # subclass TextInput, so the more specific checks MUST run first,
            # otherwise their `type="date"/"time"/"datetime-local"` attrs get
            # swallowed by the TextInput branch and the field renders as a
            # plain text box instead of a native calendar/time picker.
            #
            # We also have to set `widget.input_type` directly (not just
            # `widget.attrs['type']`), because Django's `Input.__init__`
            # already popped `type` out of attrs and stored it on
            # `input_type` at widget construction time — mutating attrs
            # afterwards has no effect on the rendered HTML.
            if isinstance(field.widget, forms.DateTimeInput):
                field.widget.input_type = "datetime-local"
                field.widget.attrs["class"] = INPUT_CLASSES
            elif isinstance(field.widget, forms.TimeInput):
                field.widget.input_type = "time"
                field.widget.attrs["class"] = INPUT_CLASSES
            elif isinstance(field.widget, forms.DateInput):
                field.widget.input_type = "date"
                field.widget.attrs["class"] = INPUT_CLASSES
            elif isinstance(field.widget, forms.TextInput):
                field.widget.attrs["class"] = INPUT_CLASSES
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs["class"] = INPUT_CLASSES
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
            "publication_status"
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
            "publication_status"
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


class ContactForm(forms.Form):
    SUBJECT_CHOICES = [
        ("general", "General Inquiry"),
        ("support", "Support & Assistance"),
        ("landlord", "Landlord Listing Support"),
        ("tenant", "Tenant Inquiries"),
        ("partnership", "Partnership & Business"),
        ("report", "Report an Issue"),
    ]

    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "Your Full Name",
        }),
        label="Full Name"
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "your.email@example.com",
        }),
        label="Email Address"
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "+233 XX XXX XXXX (Optional)",
        }),
        label="Phone Number"
    )
    subject = forms.ChoiceField(
        choices=SUBJECT_CHOICES,
        widget=forms.Select(attrs={
            "class": SELECT_CLASSES,
        }),
        label="Subject"
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": TEXTAREA_CLASSES,
            "rows": 5,
            "placeholder": "How can we help you? Please describe your request or question...",
        }),
        label="Message"
    )


class PropertyTourBookingForm(forms.Form):
    name = forms.CharField(
        max_length=120,
        required=True,
        widget=forms.TextInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "Your Full Name",
        }),
        label="Your Name"
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "your.email@example.com",
        }),
        label="Email Address"
    )
    phone = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "024 XXX XXXX or +233 XX XXX XXXX",
        }),
        label="Phone Number"
    )
    preferred_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            "class": INPUT_CLASSES,
            "type": "date",
        }),
        label="Preferred Date"
    )
    preferred_time = forms.TimeField(
        required=True,
        widget=forms.TimeInput(attrs={
            "class": INPUT_CLASSES,
            "type": "time",
        }),
        label="Preferred Time"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": TEXTAREA_CLASSES,
            "rows": 3,
            "placeholder": "Any specific requests, preferred viewing format, or questions for the landlord...",
        }),
        label="Notes / Questions (Optional)"
    )

    def clean_preferred_date(self):
        preferred_date = self.cleaned_data.get("preferred_date")
        if preferred_date and preferred_date < timezone.localdate():
            raise forms.ValidationError("Preferred date cannot be in the past.")
        return preferred_date