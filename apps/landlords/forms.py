from django import forms
from django.forms import inlineformset_factory

from apps.home_finder.models import Property, PropertyMedia


class PropertyMediaForm(forms.ModelForm):
    class Meta:
        model = PropertyMedia
        fields = [
            "file",
            "media_type",
            "caption",
            "thumbnail",
            "order",
            "is_public",
        ]


PropertyMediaFormSet = inlineformset_factory(
    Property,
    PropertyMedia,
    form=PropertyMediaForm,
    fields=("file", "media_type", "caption", "thumbnail", "order", "is_public"),
    extra=1,
    can_delete=True,
)
