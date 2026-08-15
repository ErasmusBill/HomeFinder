from django import forms
from django.db.models import Q
from django.forms import ModelForm

from apps.account.models import User
from apps.home_finder.models import PropertyInterest
from apps.notifications.models import Notification


class RecipientChoiceField(forms.ModelChoiceField):
    """Show the recipient's role alongside their name in the dropdown."""

    def label_from_instance(self, user):
        role = "Administrator" if user.is_staff or user.is_superuser else user.get_role_display()
        return f"{role} — {user.full_name} ({user.email})"


class NotificationsForm(ModelForm):
    """
    Form for creating / editing a notification. Deliberately excludes
    ``is_read`` so callers can't pre-mark a notification as read by
    hand-editing the POST body — read state is owned by the
    mark-read / mark-unread endpoints.

    The recipient choices are scoped in ``__init__``. Administrators can
    choose any user; landlords can choose administrators and only tenants
    who have expressed interest in one of their own properties.
    """

    user = RecipientChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500'
        }),
    )

    class Meta:
        model = Notification
        fields = ['title', 'content', 'user']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Notification title...'
            }),
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'rows': 4,
                'placeholder': 'Enter notification details...'
            }),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        is_admin = request_user is not None and (
            getattr(request_user, 'role', None) == User.Role.ADMIN
            or getattr(request_user, 'is_staff', False)
            or getattr(request_user, 'is_superuser', False)
        )
        if is_admin:
            self.fields['user'].queryset = User.objects.order_by('email')
        else:
            # A landlord may notify platform administrators and tenants who
            # explicitly registered interest in one of that landlord's own
            # properties — never arbitrary tenant accounts.
            interested_tenant_ids = PropertyInterest.objects.filter(
                property__landlord=request_user,
            ).values_list('tenant_id', flat=True)
            self.fields['user'].queryset = User.objects.filter(
                Q(role=User.Role.ADMIN)
                | Q(is_staff=True)
                | Q(is_superuser=True)
                | Q(id__in=interested_tenant_ids)
            ).exclude(pk=request_user.pk).distinct().order_by('role', 'full_name', 'email')
        self.fields['user'].required = True
        self.fields['user'].empty_label = "Choose a recipient"
