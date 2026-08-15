from django.test import TestCase
from django.urls import reverse

from .models import LandlordProfile, User


class AccountSettingsViewTests(TestCase):
    def test_settings_recreates_a_missing_landlord_profile(self):
        landlord = User.objects.create_user(
            email="landlord@example.com",
            full_name="Missing Profile",
            phone_number="+233200000001",
            password="test-password",
            role=User.Role.LANDLORD,
        )
        LandlordProfile.objects.filter(user=landlord).delete()
        self.client.force_login(landlord)

        response = self.client.get(reverse("account:settings"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(LandlordProfile.objects.filter(user=landlord).exists())
