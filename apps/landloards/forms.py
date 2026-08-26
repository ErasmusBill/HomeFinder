from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from apps.home_finder.forms import PropertyMediaForm, TailwindModelForm
from apps.home_finder.models import Property, PropertyMedia, LandlordDocument
from apps.tenant.models import ViewingRequest

_INPUT_CLASS = (
    "w-full px-4 py-2.5 border border-gray-300 rounded-lg bg-white "
    "text-gray-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 "
    "focus:border-emerald-500 transition"
)

PropertyMediaFormSet = inlineformset_factory(
    parent_model=Property,
    model=PropertyMedia,
    form=PropertyMediaForm,
    extra=2,
    can_delete=True
)

class BasePropertyDocumentFormSet(forms.BaseInlineFormSet):
    """
    Formset validator for property-specific documents.
    Enforces at least one document when is_required is True.
    """
    def __init__(self, *args, is_required=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_required = is_required

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        valid_doc_count = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            file_val = form.cleaned_data.get("file")
            if (form.instance and form.instance.pk and form.instance.file) or file_val:
                valid_doc_count += 1

        if self.is_required and valid_doc_count == 0:
            raise forms.ValidationError(
                "You must upload at least one property document (e.g. Proof of Ownership, Site Plan, Indenture, or Land Title) for this property listing."
            )


class PropertyDocumentForm(TailwindModelForm):
    """
    Form for uploading verification and property documents (Ghana Card, Indenture, Site Plan, Ownership, etc.)
    tied to a property listing or landlord profile.
    """
    class Meta:
        model = LandlordDocument
        fields = ["document_type", "file"]
        widgets = {
            "document_type": forms.Select(attrs={"class": _INPUT_CLASS}),
            "file": forms.FileInput(attrs={"class": _INPUT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Fetch all choices directly from the model/DB choices
        self.fields["document_type"].choices = LandlordDocument.DocumentType.choices
        self.fields["file"].required = False

    def clean(self):
        cleaned_data = super().clean()
        doc_type = cleaned_data.get("document_type")
        file_val = cleaned_data.get("file")
        is_delete = cleaned_data.get("DELETE", False)
        has_existing_instance = bool(self.instance and self.instance.pk and self.instance.file)

        # An untouched extra row (no file, no existing instance, not marked for
        # deletion) is legitimate when the landlord's Ghana Card is already
        # verified and they don't need to upload anything for this listing.
        # Skip file validation for such rows so the formset stays valid.
        if is_delete or (not file_val and not has_existing_instance):
            # Brand-new empty rows must NOT be persisted — silently marking
            # them for deletion here prevents a LandlordDocument row with
            # `file=""` from being saved, which would later crash any template
            # that renders `{{ doc.file.url }}`.
            if not has_existing_instance and not is_delete:
                cleaned_data["DELETE"] = True
            return cleaned_data

        if doc_type and not file_val:
            self.add_error("file", "Please choose a document file to upload.")

        return cleaned_data


PropertyDocumentFormSet = inlineformset_factory(
    parent_model=Property,
    model=LandlordDocument,
    form=PropertyDocumentForm,
    formset=BasePropertyDocumentFormSet,
    extra=1,
    can_delete=True
)


class LandlordIdentityDocumentForm(forms.Form):
    """
    Identity upload form (Ghana Card / National ID) for landlords.
    """
    ghana_card_file = forms.FileField(
        required=False,
        label="Ghana Card / National ID",
        help_text="Upload your Ghana Card (or National ID) once to verify your landlord identity across all your listings.",
        widget=forms.FileInput(attrs={"class": _INPUT_CLASS, "accept": ".pdf,.jpg,.jpeg,.png,.webp"})
    )

    def __init__(self, *args, is_required=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ghana_card_file"].required = is_required




# ---------------------------------------------------------------------------
# Viewing-request reschedule form (landlord)
# ---------------------------------------------------------------------------
# A narrow ModelForm so the landlord can only edit the *time* of a
# viewing request — the property, tenant, notes etc. are read-only
# here. The status is also intentionally not editable; the view flips
# status back to ``pending`` once a new date/time is saved.



class LandlordRescheduleViewingRequestForm(forms.ModelForm):
    """Landlord-side form: only the preferred date + time are editable."""

    class Meta:
        model = ViewingRequest
        fields = ["preferred_date", "preferred_time", "notes"]
        widgets = {
            "preferred_date": forms.DateInput(
                attrs={"type": "date", "class": _INPUT_CLASS},
            ),
            "preferred_time": forms.TimeInput(
                attrs={"type": "time", "class": _INPUT_CLASS},
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": _INPUT_CLASS,
                    "placeholder": "Optional note for the tenant (e.g. 'Use the side gate').",
                },
            ),
        }
        labels = {
            "preferred_date": "New preferred date",
            "preferred_time": "New preferred time",
            "notes": "Note for tenant",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notes"].required = False
        today = timezone.localdate()
        self.fields["preferred_date"].widget.attrs.update({"min": today.isoformat()})

    def clean_preferred_date(self):
        preferred_date = self.cleaned_data.get("preferred_date")
        if preferred_date and preferred_date < timezone.localdate():
            raise forms.ValidationError("New viewing date cannot be in the past.")
        return preferred_date

    def clean(self):
        cleaned_data = super().clean()
        preferred_date = cleaned_data.get("preferred_date")
        preferred_time = cleaned_data.get("preferred_time")
        today = timezone.localdate()
        current_time = timezone.localtime().time()
        if preferred_date == today and preferred_time and preferred_time <= current_time:
            self.add_error(
                "preferred_time",
                "Please pick a future time for today's viewing.",
            )
        return cleaned_data
