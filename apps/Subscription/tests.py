"""
Tests for the landlord free trial system.

Coverage is intentionally focused: the four behaviours that, if they
regress, would silently break the product.

  * ``User.is_trial_active`` / ``is_trial_expired`` /
    ``trial_days_remaining`` — the model properties that the guard,
    the context processor, and the templates all read.
  * ``start_landlord_trial`` signal helper — idempotency,
    non-landlord safety, and the concurrency lock.
  * ``landlord_has_dashboard_access`` guard — the three states
    (active paid sub / active trial / neither).
  * ``expire_landlord_free_trials`` task — the one-time-per-landlord
    guarantee that depends on the ``notified_trial_ended_at`` flag.

Things we deliberately don't test here:

  * The full Paystack payment flow. That's covered (or will be) by
    the Subscription integration tests and is orthogonal to the
    trial.
  * The Celery task email body. We use ``_send_email`` indirectly;
    the templates are integration-tested by their own app.
  * The template banner copy. Templates are integration-tested.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.account.models import User
from apps.account.signals import LANDLORD_FREE_TRIAL_DAYS, start_landlord_trial
from apps.Subscription.guards import landlord_has_dashboard_access
from apps.Subscription.models import LandlordSubscription, SubscriptionPlan
from apps.Subscription.tasks import expire_landlord_free_trials


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_landlord(*, email="landlord@example.com", phone="+233200000001", **kwargs):
    """Create a landlord with a trial already seeded by the signal.

    The post_save signal fires ``start_landlord_trial``, which deliberately
    re-fetches the row with ``select_for_update`` and writes the trial
    columns to that locked copy. The in-memory ``User`` instance returned
    by ``create_user`` therefore shows ``trial_started=False`` until we
    refresh from the database — which is exactly what callers want when
    they immediately assert on the trial columns.
    """
    user = User.objects.create_user(
        email=email,
        phone_number=phone,
        full_name=kwargs.pop("full_name", "Test Landlord"),
        password="x",
        role=User.Role.LANDLORD,
        **kwargs,
    )
    user.refresh_from_db()
    return user


def make_tenant(*, email="tenant@example.com", phone="+233200000002", **kwargs):
    return User.objects.create_user(
        email=email,
        phone_number=phone,
        full_name=kwargs.pop("full_name", "Test Tenant"),
        password="x",
        role=User.Role.TENANT,
        **kwargs,
    )


def make_admin(*, email="admin@example.com", phone="+233200000003", **kwargs):
    return User.objects.create_user(
        email=email,
        phone_number=phone,
        full_name=kwargs.pop("full_name", "Test Admin"),
        password="x",
        role=User.Role.ADMIN,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Model property tests
# ---------------------------------------------------------------------------

class TrialPropertyTests(TestCase):
    def setUp(self):
        self.landlord = make_landlord()
        # Signal seeded the trial at signup; sanity-check it.
        self.assertTrue(self.landlord.trial_started)
        self.assertIsNotNone(self.landlord.trial_end_date)

    def test_is_trial_active_is_true_for_freshly_created_landlord(self):
        self.assertTrue(self.landlord.is_trial_active)
        self.assertFalse(self.landlord.is_trial_expired)

    def test_is_trial_expired_when_window_has_passed(self):
        self.landlord.trial_end_date = timezone.now() - timedelta(days=1)
        self.assertFalse(self.landlord.is_trial_active)
        self.assertTrue(self.landlord.is_trial_expired)

    def test_is_trial_active_false_for_tenants(self):
        tenant = make_tenant()
        # Tenant has no trial columns set — both flags must be False.
        self.assertFalse(tenant.is_trial_active)
        self.assertFalse(tenant.is_trial_expired)

    def test_is_trial_active_false_for_admins(self):
        admin = make_admin()
        self.assertFalse(admin.is_trial_active)
        self.assertFalse(admin.is_trial_expired)

    def test_trial_days_remaining_is_positive_while_active(self):
        self.landlord.trial_end_date = timezone.now() + timedelta(days=5, hours=12)
        self.assertGreaterEqual(self.landlord.trial_days_remaining, 5)
        self.assertLessEqual(self.landlord.trial_days_remaining, 7)

    def test_trial_days_remaining_is_one_on_last_day(self):
        # 12 hours left should still report "1 day remaining" rather
        # than 0 — the property uses ceiling math on purpose.
        self.landlord.trial_end_date = timezone.now() + timedelta(hours=12)
        self.assertEqual(self.landlord.trial_days_remaining, 1)

    def test_trial_days_remaining_is_zero_when_expired(self):
        self.landlord.trial_end_date = timezone.now() - timedelta(days=1)
        self.assertEqual(self.landlord.trial_days_remaining, 0)

    def test_was_ever_granted_trial(self):
        self.assertTrue(self.landlord.was_ever_granted_trial)
        # After "expiry" the flag stays True (history preserved).
        self.landlord.trial_end_date = timezone.now() - timedelta(days=1)
        self.assertTrue(self.landlord.was_ever_granted_trial)
        # But for a landlord who never had a trial, it's False.
        bare = make_landlord(email="bare@example.com", phone="+233200000099")
        bare.trial_started = False
        bare.trial_start_date = None
        bare.trial_end_date = None
        self.assertFalse(bare.was_ever_granted_trial)

    def test_trial_default_length_is_30_days(self):
        self.assertEqual(LANDLORD_FREE_TRIAL_DAYS, 30)
        delta = self.landlord.trial_end_date - self.landlord.trial_start_date
        self.assertEqual(delta.days, 30)


# ---------------------------------------------------------------------------
# Signal helper tests
# ---------------------------------------------------------------------------

class StartLandlordTrialTests(TestCase):
    def test_signal_seeds_trial_at_signup(self):
        landlord = make_landlord(
            email="signal@example.com", phone="+233200000010"
        )
        # post_save fired; trial must be seeded.
        self.assertTrue(landlord.trial_started)
        self.assertIsNotNone(landlord.trial_start_date)
        self.assertIsNotNone(landlord.trial_end_date)

    def test_start_landlord_trial_is_idempotent(self):
        landlord = make_landlord(
            email="idemp@example.com", phone="+233200000011"
        )
        original_end = landlord.trial_end_date
        # Calling again on a landlord who already has a trial is a no-op.
        result = start_landlord_trial(landlord)
        self.assertFalse(result)
        landlord.refresh_from_db()
        self.assertEqual(landlord.trial_end_date, original_end)

    def test_start_landlord_trial_skips_non_landlords(self):
        tenant = make_tenant()
        result = start_landlord_trial(tenant)
        self.assertFalse(result)
        tenant.refresh_from_db()
        self.assertFalse(tenant.trial_started)
        self.assertIsNone(tenant.trial_end_date)

    def test_start_landlord_trial_resets_notification_flag(self):
        # If a trial is re-seeded (e.g. admin repair), the
        # ``notified_trial_ended_at`` flag must be cleared so the
        # next "your trial has ended" email can fire.
        landlord = make_landlord(
            email="reset@example.com", phone="+233200000012"
        )
        User.objects.filter(pk=landlord.pk).update(
            notified_trial_ended_at=timezone.now() - timedelta(days=1),
            trial_started=False,
            trial_end_date=None,
        )
        landlord.refresh_from_db()
        # Confirm the precondition: flag is set, trial is not.
        self.assertIsNotNone(landlord.notified_trial_ended_at)
        self.assertFalse(landlord.trial_started)
        # Re-seed.
        result = start_landlord_trial(landlord)
        self.assertTrue(result)
        landlord.refresh_from_db()
        self.assertIsNone(landlord.notified_trial_ended_at)
        self.assertTrue(landlord.trial_started)


# ---------------------------------------------------------------------------
# Role-transition tests
#
# A user who signs up as a tenant and is later promoted to landlord
# (or whose role is otherwise changed post-signup) must end up with
# a 30-day free trial seeded by the post_save signal, exactly as if
# they had signed up as a landlord from the start.
# ---------------------------------------------------------------------------

class RoleTransitionTrialTests(TestCase):
    def test_tenant_promoted_to_landlord_gets_trial(self):
        tenant = make_tenant(email="promote@example.com", phone="+233200000030")
        # Sanity: tenants don't have a trial by default.
        self.assertFalse(tenant.trial_started)
        self.assertIsNone(tenant.trial_end_date)
        # Promote.
        tenant.role = User.Role.LANDLORD
        tenant.save()
        tenant.refresh_from_db()
        # Trial must now be seeded.
        self.assertTrue(tenant.trial_started)
        self.assertIsNotNone(tenant.trial_start_date)
        self.assertIsNotNone(tenant.trial_end_date)
        self.assertTrue(tenant.is_trial_active)
        # The window should be ~30 days, not 0.
        delta = tenant.trial_end_date - tenant.trial_start_date
        self.assertEqual(delta.days, 30)

    def test_ordinary_landlord_update_does_not_reseed_trial(self):
        landlord = make_landlord(
            email="update@example.com", phone="+233200000031"
        )
        original_end = landlord.trial_end_date
        # Update an unrelated field — should NOT reset the trial.
        landlord.full_name = "Updated Name"
        landlord.save()
        landlord.refresh_from_db()
        self.assertEqual(landlord.trial_end_date, original_end)
        self.assertTrue(landlord.trial_started)

    def test_admin_revoke_then_save_does_not_undo_revoke(self):
        # Scenario: support runs ``manage_trial revoke`` on a
        # landlord. That command clears ``trial_started`` and
        # ``trial_end_date`` and saves the row. Without the
        # previous-role check, our new post_save branch would
        # see ``role='landlord'`` and re-seed the trial,
        # undoing the revoke. With the check, the previous
        # role is already 'landlord' so the seed is skipped.
        landlord = make_landlord(
            email="revoke@example.com", phone="+233200000032"
        )
        # Simulate the revoke command.
        User.objects.filter(pk=landlord.pk).update(
            trial_started=False,
            trial_start_date=None,
            trial_end_date=None,
            notified_trial_ended_at=None,
        )
        landlord.refresh_from_db()
        self.assertFalse(landlord.trial_started)
        # Now save again with no role change. Trial must stay
        # empty — the revoke should not be silently undone.
        landlord.full_name = "Still Revoked"
        landlord.save()
        landlord.refresh_from_db()
        self.assertFalse(landlord.trial_started)
        self.assertIsNone(landlord.trial_end_date)

    def test_promoted_tenant_lands_in_guard_access(self):
        # End-to-end: after promotion, the guard must let the
        # landlord into the dashboard via the trial branch.
        from apps.Subscription.guards import landlord_has_dashboard_access
        tenant = make_tenant(email="e2e@example.com", phone="+233200000033")
        self.assertFalse(landlord_has_dashboard_access(tenant))
        tenant.role = User.Role.LANDLORD
        tenant.save()
        tenant.refresh_from_db()
        self.assertTrue(landlord_has_dashboard_access(tenant))


# ---------------------------------------------------------------------------
# Guard tests
# ---------------------------------------------------------------------------

class LandlordHasDashboardAccessTests(TestCase):
    def setUp(self):
        self.landlord_with_active_trial = make_landlord(
            email="trial@example.com", phone="+233200000020"
        )
        self.expired_landlord = make_landlord(
            email="expired@example.com", phone="+233200000021"
        )
        self.expired_landlord.trial_end_date = timezone.now() - timedelta(days=1)
        self.expired_landlord.save(update_fields=["trial_end_date"])

        self.admin = make_admin()

    def test_admin_always_has_access(self):
        self.assertTrue(landlord_has_dashboard_access(self.admin))

    def test_landlord_with_active_trial_has_access(self):
        self.assertTrue(landlord_has_dashboard_access(self.landlord_with_active_trial))

    def test_landlord_with_expired_trial_loses_access(self):
        self.assertFalse(landlord_has_dashboard_access(self.expired_landlord))

    def test_tenant_never_has_landlord_access(self):
        tenant = make_tenant()
        self.assertFalse(landlord_has_dashboard_access(tenant))

    def test_landlord_with_active_paid_sub_has_access_even_if_trial_expired(self):
        # Even with an expired trial, an active paid subscription
        # keeps the landlord in. This is the order-dependent rule
        # the guard documents: paid sub beats trial.
        plan = SubscriptionPlan.objects.create(
            name="Basic", price=10, duration_days=30, maximum_listings=5,
        )
        sub = LandlordSubscription.objects.create(
            landlord=self.expired_landlord, plan=plan,
        )
        sub.activate()
        self.assertTrue(landlord_has_dashboard_access(self.expired_landlord))

    def test_anonymous_user_has_no_access(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(landlord_has_dashboard_access(AnonymousUser()))


class PaystackCallbackRedirectTests(TestCase):
    def test_confirmed_payment_redirects_to_the_landlord_subscription_page(self):
        landlord = make_landlord(
            email="callback@example.com", phone="+233200000050"
        )
        plan = SubscriptionPlan.objects.create(
            name="Callback plan", price=10, duration_days=30, maximum_listings=5,
        )
        subscription = LandlordSubscription.objects.create(
            landlord=landlord,
            plan=plan,
            payment_reference="callback-reference",
        )
        subscription.activate()
        self.client.force_login(landlord)

        response = self.client.get(
            reverse("subscription:paystack_callback"),
            {"reference": subscription.payment_reference},
        )

        self.assertRedirects(
            response,
            reverse("landloards:list_landlord_subscription"),
            fetch_redirect_response=False,
        )


# ---------------------------------------------------------------------------
# Daily expiry task — one-time-per-landlord guarantee
# ---------------------------------------------------------------------------

class ExpireLandlordFreeTrialsTests(TestCase):
    def setUp(self):
        # Landlord whose trial has just ended, never notified.
        self.expired = make_landlord(
            email="expired-task@example.com", phone="+233200000030"
        )
        self.expired.trial_end_date = timezone.now() - timedelta(hours=1)
        self.expired.save(update_fields=["trial_end_date"])

        # Landlord whose trial is still running.
        self.active = make_landlord(
            email="active@example.com", phone="+233200000031"
        )

        # Landlord whose trial already ended AND was already notified.
        self.already_notified = make_landlord(
            email="notified@example.com", phone="+233200000032"
        )
        self.already_notified.trial_end_date = timezone.now() - timedelta(days=2)
        self.already_notified.notified_trial_ended_at = timezone.now() - timedelta(days=1)
        self.already_notified.save(update_fields=[
            "trial_end_date", "notified_trial_ended_at",
        ])

    @patch("apps.Subscription.tasks.send_trial_ended_email_task")
    def test_emails_only_landlords_with_ended_and_unnotified_trials(self, mock_send):
        mock_send.delay.return_value = None
        # Patch ``on_commit`` to run immediately so we can assert.
        from django.db import transaction
        real_on_commit = transaction.on_commit
        transaction.on_commit = lambda fn, using=None, robust=False: fn()
        try:
            processed = expire_landlord_free_trials()
        finally:
            transaction.on_commit = real_on_commit

        self.assertEqual(processed, 1)
        mock_send.delay.assert_called_once()
        # And the right landlord was passed.
        args, _ = mock_send.delay.call_args
        self.assertEqual(args[0], self.expired.id)

    @patch("apps.Subscription.tasks.send_trial_ended_email_task")
    def test_marks_notified_flag_after_dispatch(self, mock_send):
        mock_send.delay.return_value = None
        from django.db import transaction
        real_on_commit = transaction.on_commit
        transaction.on_commit = lambda fn, using=None, robust=False: fn()
        try:
            expire_landlord_free_trials()
        finally:
            transaction.on_commit = real_on_commit

        self.expired.refresh_from_db()
        self.assertIsNotNone(self.expired.notified_trial_ended_at)
        # Already-notified landlord is untouched.
        self.already_notified.refresh_from_db()
        # The pre-existing flag stays put (the task skipped this row).
        self.assertIsNotNone(self.already_notified.notified_trial_ended_at)

    @patch("apps.Subscription.tasks.send_trial_ended_email_task")
    def test_running_trial_is_not_notified(self, mock_send):
        mock_send.delay.return_value = None
        from django.db import transaction
        real_on_commit = transaction.on_commit
        transaction.on_commit = lambda fn, using=None, robust=False: fn()
        try:
            processed = expire_landlord_free_trials()
        finally:
            transaction.on_commit = real_on_commit

        # The active-trial landlord must not have been notified.
        self.active.refresh_from_db()
        self.assertIsNone(self.active.notified_trial_ended_at)
        # And they were not counted.
        self.assertEqual(processed, 1)

    @patch("apps.Subscription.tasks.send_trial_ended_email_task")
    def test_second_run_does_not_double_email(self, mock_send):
        mock_send.delay.return_value = None
        from django.db import transaction
        real_on_commit = transaction.on_commit
        transaction.on_commit = lambda fn, using=None, robust=False: fn()
        try:
            expire_landlord_free_trials()
            # Reset the mock so the second call's assertions are clean.
            mock_send.reset_mock()
            processed_second = expire_landlord_free_trials()
        finally:
            transaction.on_commit = real_on_commit

        # Second run: nobody left to notify, nothing dispatched.
        self.assertEqual(processed_second, 0)
        mock_send.delay.assert_not_called()
