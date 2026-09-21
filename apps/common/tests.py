from django.test import TestCase, RequestFactory
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.common.admin_analytics import get_admin_dashboard_context
from apps.home_finder.models import Property, Region, District, Town, Area
from apps.Subscription.models import SubscriptionPlan, LandlordSubscription

User = get_user_model()


class AdminDashboardAnalyticsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        # Create Admin
        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            full_name="Super Admin",
            password="adminpassword123",
        )

        # Create Tenant & Landlord
        self.tenant = User.objects.create_user(
            email="tenant1@example.com",
            full_name="Test Tenant",
            password="password123",
            role=User.Role.TENANT,
        )
        self.landlord = User.objects.create_user(
            email="landlord1@example.com",
            full_name="Test Landlord",
            password="password123",
            role=User.Role.LANDLORD,
        )

        # Create Location Hierarchy
        self.region = Region.objects.create(name="Greater Accra")
        self.district = District.objects.create(name="Accra Metro", region=self.region)
        self.town = Town.objects.create(name="Osu", district=self.district)
        self.area = Area.objects.create(name="Ringway", town=self.town)

        # Create Properties (1 Verified, 1 Pending)
        self.prop_verified = Property.objects.create(
            landlord=self.landlord,
            title="Verified Luxury Apartment",
            description="Nice place",
            price=2500,
            payment_period=Property.PaymentPeriod.MONTHLY,
            room_type=Property.RoomType.APARTMENT,
            region=self.region,
            district=self.district,
            town=self.town,
            area=self.area,
            verification_status=Property.VerificationStatus.VERIFIED,
            publication_status=Property.PublicationStatus.PUBLISHED,
        )

        self.prop_pending = Property.objects.create(
            landlord=self.landlord,
            title="Pending Chamber and Hall",
            description="Pending verification",
            price=800,
            payment_period=Property.PaymentPeriod.MONTHLY,
            room_type=Property.RoomType.CHAMBER_AND_HALL,
            region=self.region,
            district=self.district,
            town=self.town,
            area=self.area,
            verification_status=Property.VerificationStatus.PENDING,
            publication_status=Property.PublicationStatus.DRAFT,
        )

        # Create Plan & Subscription
        self.plan = SubscriptionPlan.objects.create(
            name="Premium Landlord",
            price=150.00,
            duration_days=30,
            maximum_listings=10,
        )
        self.sub = LandlordSubscription.objects.create(
            landlord=self.landlord,
            plan=self.plan,
            status=LandlordSubscription.Status.SUCCESS,
            is_active=True,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=30),
            payment_reference="PAY-TEST-123456",
        )

    def test_get_admin_dashboard_context(self):
        context = get_admin_dashboard_context()

        # Check KPI counts
        self.assertEqual(context["stats_total_tenants"], 1)
        self.assertEqual(context["stats_total_landlords"], 1)
        self.assertEqual(context["stats_approved_properties"], 1)
        self.assertEqual(context["stats_pending_properties"], 1)
        self.assertEqual(context["stats_total_properties"], 2)
        self.assertGreaterEqual(float(context["stats_total_revenue"]), 150.0)
        self.assertEqual(context["stats_active_subscriptions"], 1)

        # Check tables
        self.assertTrue(any(tx["reference"] == "PAY-TEST-123456" for tx in context["transaction_records"]))
        self.assertTrue(any(p["id"] == self.prop_pending.id for p in context["pending_properties_records"]))

    def test_admin_index_view_renders_dashboard_context(self):
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("stats_total_tenants", response.context[-1] if isinstance(response.context, list) else response.context)
        self.assertContains(response, "Executive Overview")
        self.assertContains(response, "Pending Properties")
        self.assertContains(response, "Approved Properties")
        self.assertContains(response, "PAY-TEST-123456")

    def test_admin_dashboard_filters(self):
        # Test timeframe filter
        request_today = self.factory.get("/admin/?timeframe=today")
        ctx_today = get_admin_dashboard_context(request=request_today)
        self.assertEqual(ctx_today["timeframe"], "today")
        self.assertEqual(ctx_today["stats_total_tenants"], 1)

        # Test region filter
        request_region = self.factory.get(f"/admin/?region={self.region.id}")
        ctx_region = get_admin_dashboard_context(request=request_region)
        self.assertEqual(ctx_region["selected_region"], str(self.region.id))
        self.assertEqual(ctx_region["stats_total_properties"], 2)

        # Test property_status filter
        request_verified = self.factory.get("/admin/?property_status=verified")
        ctx_verified = get_admin_dashboard_context(request=request_verified)
        self.assertEqual(ctx_verified["selected_property_status"], "verified")
        self.assertEqual(ctx_verified["stats_total_properties"], 1)
        self.assertEqual(ctx_verified["stats_approved_properties"], 1)


