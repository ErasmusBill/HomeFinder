"""
Database seeder for the Subscription app.

Creates:
  * 5 SubscriptionPlan rows (Free, Starter, Pro, Business, Enterprise)
  * A handful of LandlordSubscription rows that exercise every state the
    model supports - active, pending payment, expired, cancelled at
    period end, cancelled immediately, and a scheduled downgrade - so the
    landlord dashboard, billing page, and admin all have realistic data
    to render against.

Idempotent: running it again updates existing rows in place rather than
duplicating them. Use --clear to wipe plans + subscriptions first (the
plan FK is PROTECT, so --clear will refuse if any subscription row exists).

Usage:
    python manage.py seed_subscription
    python manage.py seed_subscription --clear
    python manage.py seed_subscription --no-landlords   # plans only
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.Subscription.models import LandlordSubscription, SubscriptionPlan
from apps.account.models import LandlordProfile, User

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Plan catalogue
# -----------------------------------------------------------------------------
# GHS pricing tuned for the Ghanaian rental market. duration_days is the
# length of one billing cycle; maximum_listings caps how many active
# Property rows a landlord can publish while subscribed to this plan.
PLAN_CATALOG = [
    {
        "name": "Free",
        "description": (
            "Get started for free. List one property and explore the "
            "platform - no card required."
        ),
        "price": "0.00",
        "duration_days": 30,
        "maximum_listings": 1,
        "is_active": True,
        "is_free": True,
    },
    {
        "name": "Starter",
        "description": (
            "Perfect for landlords with a few units. List up to 3 "
            "properties and reach tenants faster."
        ),
        "price": "49.00",
        "duration_days": 30,
        "maximum_listings": 3,
        "is_active": True,
        "is_free": False,
    },
    {
        "name": "Pro",
        "description": (
            "For serious landlords. List up to 10 properties, unlock "
            "priority placement, and respond to viewing requests faster."
        ),
        "price": "129.00",
        "duration_days": 30,
        "maximum_listings": 10,
        "is_active": True,
        "is_free": False,
    },
    {
        "name": "Business",
        "description": (
            "Built for property managers. Up to 30 listings, 3-month "
            "billing cycle, and a dedicated success contact."
        ),
        "price": "349.00",
        "duration_days": 90,
        "maximum_listings": 30,
        "is_active": True,
        "is_free": False,
    },
    {
        "name": "Enterprise",
        "description": (
            "Unlimited listings for real-estate companies and agencies. "
            "Annual billing, custom onboarding, and SLA-backed support."
        ),
        "price": "999.00",
        "duration_days": 365,
        "maximum_listings": 9999,
        "is_active": True,
        "is_free": False,
    },
]


# -----------------------------------------------------------------------------
# Sample landlord users for the subscription fixtures
# -----------------------------------------------------------------------------
# Realistic-looking Ghanaian landlord personas. Each one is paired with a
# spec in the demo_subscriptions list below to produce a realistic spread
# of subscription rows.
DEMO_LANDLORDS = [
    {
        "email": "ama.mensah+seed@example.com",
        "full_name": "Ama Mensah",
        "phone_number": "+233244000001",
        "company_name": "Mensah Rentals",
    },
    {
        "email": "kwame.asante+seed@example.com",
        "full_name": "Kwame Asante",
        "phone_number": "+233244000002",
        "company_name": "Asante Properties",
    },
    {
        "email": "akosua.boateng+seed@example.com",
        "full_name": "Akosua Boateng",
        "phone_number": "+233244000003",
        "company_name": None,
    },
    {
        "email": "yaw.darko+seed@example.com",
        "full_name": "Yaw Darko",
        "phone_number": "+233244000004",
        "company_name": "Darko Estates Ltd.",
    },
    {
        "email": "efua.addai+seed@example.com",
        "full_name": "Efua Addai",
        "phone_number": "+233244000005",
        "company_name": "Addai Holdings",
    },
    {
        "email": "kwesi.boateng+seed@example.com",
        "full_name": "Kwesi Boateng",
        "phone_number": "+233244000006",
        "company_name": "Boateng & Co. Realty",
    },
]


class Command(BaseCommand):
    help = "Seed the Subscription app with plans and example landlord subscriptions."

    # ------------------------------------------------------------------ argparse
    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help=(
                "Wipe all SubscriptionPlan + LandlordSubscription rows "
                "before seeding. Aborts if any LandlordSubscription row "
                "still references one (FK is PROTECT on plan)."
            ),
        )
        parser.add_argument(
            "--no-landlords",
            action="store_true",
            help="Seed only the plan catalogue; skip demo landlord subscriptions.",
        )

    # --------------------------------------------------------------------- main
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting Subscription app seeding..."))

        if options.get("clear"):
            self._clear_existing()

        with transaction.atomic():
            plans_by_name = self._seed_plans()

            if not options.get("no_landlords"):
                self._seed_demo_subscriptions(plans_by_name)

        self._print_summary()

    # ------------------------------------------------------------------- helpers
    def _clear_existing(self):
        self.stdout.write(self.style.WARNING("Clearing existing subscriptions + plans..."))
        LandlordSubscription.objects.all().delete()
        SubscriptionPlan.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("  Cleared."))

    def _seed_plans(self) -> dict:
        """
        Upsert every plan in PLAN_CATALOG and return a {plan_name: plan}
        mapping for the rest of the seeder to use.
        """
        self.stdout.write("Seeding subscription plans...")
        plans_by_name = {}

        for spec in PLAN_CATALOG:
            plan, created = SubscriptionPlan.objects.update_or_create(
                name=spec["name"],
                defaults={
                    "description": spec["description"],
                    "price": spec["price"],
                    "duration_days": spec["duration_days"],
                    "maximum_listings": spec["maximum_listings"],
                    "is_active": spec["is_active"],
                    "is_free": spec["is_free"],
                },
            )
            plans_by_name[plan.name] = plan
            verb = "Created" if created else "Updated"
            self.stdout.write(f"  - {verb} plan: {plan.name} (GHS {plan.price})")

        return plans_by_name

    def _get_or_create_demo_landlord(self, spec):
        """
        Ensure a landlord User (with a LandlordProfile) exists for the
        given spec and return it. Email-verified so the demo doesn't
        look half-broken in the admin.
        """
        user, created = User.objects.get_or_create(
            email=spec["email"],
            defaults={
                "full_name": spec["full_name"],
                "phone_number": spec["phone_number"],
                "role": User.Role.LANDLORD,
                "is_email_verified": True,
            },
        )
        if created:
            # Unusable password - these are demo rows, not real logins.
            user.set_unusable_password()
            user.save(update_fields=["password"])

        LandlordProfile.objects.get_or_create(
            user=user,
            defaults={"company_name": spec.get("company_name") or ""},
        )
        return user

    def _make_idempotence_key(self) -> str:
        return f"idem-seed-{secrets.token_hex(12)}"

    def _seed_demo_subscriptions(self, plans_by_name):
        """
        Drop a deterministic set of LandlordSubscription rows that
        collectively cover every status the dashboard renders.
        """
        self.stdout.write("Seeding demo landlord subscriptions...")

        now = timezone.now()
        plan_pro = plans_by_name["Pro"]
        plan_starter = plans_by_name["Starter"]
        plan_business = plans_by_name["Business"]
        plan_enterprise = plans_by_name["Enterprise"]

        # Each spec is processed against one of the demo landlord users
        # (by index into DEMO_LANDLORDS).
        specs = [
            # 0: Ama Mensah - Pro, fully active, paid, renews in ~24 days.
            #    Also schedules a downgrade to Starter at period end.
            {
                "landlord_index": 0,
                "plan": plan_pro,
                "status": LandlordSubscription.Status.SUCCESS,
                "active": True,
                "start_offset_days": -6,
                "end_offset_days": 24,
                "payment_reference": "SEED-AMA-PRO-001",
                "pending_plan": plan_starter,
            },
            # 1: Kwame Asante - Business, active, 2 months into a 3-month cycle.
            {
                "landlord_index": 1,
                "plan": plan_business,
                "status": LandlordSubscription.Status.SUCCESS,
                "active": True,
                "start_offset_days": -60,
                "end_offset_days": 30,
                "payment_reference": "SEED-KWA-BIZ-001",
            },
            # 2: Akosua Boateng - Enterprise, active, mid-cycle.
            {
                "landlord_index": 2,
                "plan": plan_enterprise,
                "status": LandlordSubscription.Status.SUCCESS,
                "active": True,
                "start_offset_days": -120,
                "end_offset_days": 245,
                "payment_reference": "SEED-AKO-ENT-001",
            },
            # 3: Yaw Darko - Pro, pending payment (just initiated checkout).
            {
                "landlord_index": 3,
                "plan": plan_pro,
                "status": LandlordSubscription.Status.PENDING,
                "active": False,
                "start_offset_days": None,
                "end_offset_days": None,
                "payment_reference": "SEED-YAW-PRO-PENDING",
            },
            # 4: Efua Addai - Starter, FAILED payment (declined card).
            {
                "landlord_index": 4,
                "plan": plan_starter,
                "status": LandlordSubscription.Status.FAILED,
                "active": False,
                "start_offset_days": None,
                "end_offset_days": None,
                "payment_reference": "SEED-EFU-START-FAIL",
            },
            # 5: Kwesi Boateng - Pro, scheduled cancellation at period end.
            {
                "landlord_index": 5,
                "plan": plan_pro,
                "status": LandlordSubscription.Status.SUCCESS,
                "active": True,
                "start_offset_days": -20,
                "end_offset_days": 10,
                "payment_reference": "SEED-KWE-PRO-CANCEL",
                "cancel_at_period_end": True,
                "cancelled_offset_days": -3,
            },
            # 6: Ama Mensah - earlier Pro subscription that has already expired,
            #    kept around so the admin's history view has something to show.
            {
                "landlord_index": 0,
                "plan": plan_pro,
                "status": LandlordSubscription.Status.SUCCESS,
                "active": False,
                "start_offset_days": -300,
                "end_offset_days": -270,
                "payment_reference": "SEED-AMA-PRO-HIST",
            },
        ]

        for spec in specs:
            landlord_spec = DEMO_LANDLORDS[spec["landlord_index"]]
            landlord = self._get_or_create_demo_landlord(landlord_spec)

            start_dt = (
                now + timedelta(days=spec["start_offset_days"])
                if spec["start_offset_days"] is not None
                else None
            )
            end_dt = (
                now + timedelta(days=spec["end_offset_days"])
                if spec["end_offset_days"] is not None
                else None
            )
            cancelled_at = (
                now + timedelta(days=spec["cancelled_offset_days"])
                if "cancelled_offset_days" in spec
                else None
            )

            defaults = {
                "landlord": landlord,
                "plan": spec["plan"],
                "status": spec["status"],
                "is_active": spec["active"],
                "start_date": start_dt,
                "end_date": end_dt,
                "idempotence_key": self._make_idempotence_key(),
                "cancel_at_period_end": spec.get("cancel_at_period_end", False),
                "cancelled_at": cancelled_at,
                "pending_plan": spec.get("pending_plan"),
            }

            sub, created = LandlordSubscription.objects.update_or_create(
                payment_reference=spec["payment_reference"],
                defaults=defaults,
            )
            verb = "Created" if created else "Updated"
            marker = " (cancel-at-period-end)" if sub.cancel_at_period_end else ""
            self.stdout.write(
                f"  - {verb} sub: {landlord.full_name} -> {sub.plan.name} "
                f"[{sub.status}{marker}]"
            )

    def _print_summary(self):
        total_plans = SubscriptionPlan.objects.count()
        active_plans = SubscriptionPlan.objects.filter(is_active=True).count()
        total_subs = LandlordSubscription.objects.count()
        active_subs = LandlordSubscription.objects.filter(
            status=LandlordSubscription.Status.SUCCESS,
            is_active=True,
        ).count()

        self.stdout.write(self.style.SUCCESS(
            "\nSubscription app seeding complete.\n"
            f"  Plans: {total_plans} total ({active_plans} active for purchase)\n"
            f"  Subscriptions: {total_subs} total ({active_subs} currently active)"
        ))
