from django.test import TestCase

from apps.account.models import User
from apps.notifications.forms import NotificationsForm


class NotificationRecipientFormTests(TestCase):
    def test_landlord_can_select_an_administrator_as_recipient(self):
        landlord = User.objects.create_user(
            email="landlord@example.com",
            full_name="Landlord User",
            phone_number="+233200000010",
            password="test-password",
            role=User.Role.LANDLORD,
        )
        administrator = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            phone_number="+233200000011",
            password="test-password",
            role=User.Role.ADMIN,
        )

        form = NotificationsForm(request_user=landlord)

        self.assertIn("user", form.fields)
        self.assertEqual(list(form.fields["user"].queryset), [administrator])
