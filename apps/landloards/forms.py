from django.forms import inlineformset_factory

from apps.home_finder.forms import PropertyMediaForm
from apps.home_finder.models import Property, PropertyMedia

PropertyMediaFormSet = inlineformset_factory(
    parent_model=Property,
    model=PropertyMedia,
    form=PropertyMediaForm,
    extra=2,
    can_delete=True
)