from django.test import TestCase, RequestFactory
from django.urls import reverse
from allauth.socialaccount.models import SocialAccount, SocialLogin

from .models import LandlordProfile, TenantProfile, User
from .adapter import CustomSocialAccountAdapter


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


class UserModelAndSocialLoginTests(TestCase):
    def test_multiple_users_with_blank_or_none_phone_number(self):
        """Verify that multiple users can be created without a phone number without IntegrityError."""
        user1 = User.objects.create_user(
            email="user1@example.com",
            full_name="User One",
            phone_number="",
            password="password123",
        )
        user2 = User.objects.create_user(
            email="user2@example.com",
            full_name="User Two",
            phone_number=None,
            password="password123",
        )
        user3 = User.objects.create(
            email="user3@example.com",
            first_name="User",
            last_name="Three",
            phone_number="",
        )

        user1.refresh_from_db()
        user2.refresh_from_db()
        user3.refresh_from_db()

        self.assertIsNone(user1.phone_number)
        self.assertIsNone(user2.phone_number)
        self.assertIsNone(user3.phone_number)
        self.assertEqual(user3.full_name, "User Three")

    def test_custom_social_account_adapter_populate_user(self):
        """Verify adapter populates full_name, verified email, and phone_number=None."""
        adapter = CustomSocialAccountAdapter()
        user = User()
        account = SocialAccount(provider='google', uid='10001')
        sociallogin = SocialLogin(user=user, account=account)
        data = {
            'email': 'socialuser@gmail.com',
            'name': 'Google User',
            'first_name': 'Google',
            'last_name': 'User',
        }

        user = adapter.populate_user(None, sociallogin, data)
        user.save()

        self.assertEqual(user.email, 'socialuser@gmail.com')
        self.assertEqual(user.full_name, 'Google User')
        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.phone_number)

    def test_landlord_social_signup_assigns_landlord_role_and_trial(self):
        """Verify social registration with role=landlord creates Landlord user, LandlordProfile, and seeds 30-day trial."""
        factory = RequestFactory()
        request = factory.get('/account/register/?role=landlord')
        request.session = {'social_signup_role': 'landlord'}

        adapter = CustomSocialAccountAdapter()
        user = User()
        account = SocialAccount(provider='google', uid='20002')
        sociallogin = SocialLogin(user=user, account=account)
        data = {
            'email': 'landlord_social@gmail.com',
            'name': 'Landlord Google User',
        }

        user = adapter.populate_user(request, sociallogin, data)
        user = adapter.save_user(request, sociallogin)
        user.refresh_from_db()

        self.assertEqual(user.role, User.Role.LANDLORD)
        self.assertTrue(LandlordProfile.objects.filter(user=user).exists())
        self.assertTrue(user.trial_started)
        self.assertTrue(user.is_trial_active)

        # Verify login redirect points to landlord dashboard
        request.user = user
        redirect_url = adapter.get_login_redirect_url(request)
        self.assertEqual(redirect_url, reverse('landloards:landloards_dashboard'))

    def test_tenant_social_signup_assigns_tenant_role(self):
        """Verify social registration with role=tenant creates Tenant user and TenantProfile."""
        factory = RequestFactory()
        request = factory.get('/account/register/?role=tenant')
        request.session = {'social_signup_role': 'tenant'}

        adapter = CustomSocialAccountAdapter()
        user = User()
        account = SocialAccount(provider='facebook', uid='30003')
        sociallogin = SocialLogin(user=user, account=account)
        data = {
            'email': 'tenant_social@gmail.com',
            'name': 'Tenant Facebook User',
        }

        user = adapter.populate_user(request, sociallogin, data)
        user = adapter.save_user(request, sociallogin)
        user.refresh_from_db()

        self.assertEqual(user.role, User.Role.TENANT)
        self.assertTrue(TenantProfile.objects.filter(user=user).exists())

        # Verify login redirect points to tenant dashboard
        request.user = user
        redirect_url = adapter.get_login_redirect_url(request)
        self.assertEqual(redirect_url, reverse('tenant:dashboard'))
