from django import forms
from django.forms import ModelForm

from apps.account.models import User
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

    The recipient choices are scoped to fetch all users in the system.
    """

    user = RecipientChoiceField(
        queryset=None,
        required=True,
        empty_label="Choose a recipient",
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

        # Fetch all users in the system, optionally excluding the current user if needed,
        # ordered cleanly by role, full name, and email.
        queryset = User.objects.all().order_by('role', 'full_name', 'email')

        if request_user and request_user.pk:
            queryset = queryset.exclude(pk=request_user.pk)

        self.fields['user'].queryset = queryset