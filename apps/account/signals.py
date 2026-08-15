import logging
from datetime import timedelta

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import User, TenantProfile, LandlordProfile

logger = logging.getLogger(__name__)

# Free-trial length for new landlords. Centralised here so the dashboard,
# guard, and admin notes all show the same number. Per the spec this is
# "one month only" — modelled as 30 days to match the existing monthly
# billing period in SubscriptionPlan.duration_days.
LANDLORD_FREE_TRIAL_DAYS = 30


def start_landlord_trial(landlord, *, now=None):
    """
    Idempotently seed a 30-day free trial on ``landlord``.

    Skips landlords who already have a trial window (``trial_started=True``)
    so this is safe to call from multiple places — the data migration,
    a future management command, or the post_save signal. Returns True
    if a trial was started, False if the landlord already had one.

    Race-safety: wrapped in ``transaction.atomic`` with a
    ``select_for_update`` on the landlord row. Without this, two
    concurrent ``post_save`` signals (e.g. during a bulk import) can
    both read ``trial_started=False`` and both write a fresh trial
    window, double-seeding the trial. The lock + the in-memory
    ``trial_started`` check together make the function truly
    idempotent under concurrency.

    ``now`` is accepted as a parameter so tests can pin the clock.
    """
    if landlord.role != User.Role.LANDLORD:
        return False
    if landlord.trial_started:
        return False

    moment = now or timezone.now()
    try:
        with transaction.atomic():
            # Re-fetch with a row lock so a concurrent caller can't
            # also pass the ``trial_started`` check above.
            locked = (
                User.objects
                .select_for_update()
                .get(pk=landlord.pk)
            )
            if locked.trial_started:
                # Another worker beat us to it between the
                # in-memory check and the lock.
                return False
            locked.trial_start_date = moment
            locked.trial_end_date = moment + timedelta(days=LANDLORD_FREE_TRIAL_DAYS)
            locked.trial_started = True
            # Reset the "trial-ended email" timestamp so a re-seeded
            # trial can fire the expiry email again at the end of the
            # new window. Without this, a landlord whose trial was
            # reset would never get the next "your trial has ended"
            # notification (the daily task would see
            # ``notified_trial_ended_at IS NOT NULL`` and skip them).
            locked.notified_trial_ended_at = None
            locked.save(update_fields=[
                "trial_start_date",
                "trial_end_date",
                "trial_started",
                "notified_trial_ended_at",
            ])
    except Exception:
        # We deliberately do NOT swallow the exception silently:
        # a landlord with no trial row would be silently blocked
        # from the dashboard, which is a much worse failure mode
        # than a loud signup error. Log and re-raise so the
        # registration view surfaces a 500 to the user (and to
        # Sentry / logs) instead of creating a half-broken
        # account.
        logger.exception(
            "start_landlord_trial: failed to seed trial for landlord %s",
            getattr(landlord, "pk", None),
        )
        raise

    return True


@receiver(pre_save, sender=User)
def _stash_previous_role(sender, instance, **kwargs):
    """
    Capture the role currently stored in the database onto the
    instance so the post_save handler can detect a
    tenant→landlord transition (or any other role change).

    Only runs for updates (``instance.pk`` is set). For new users,
    ``instance._previous_role`` is set to None and the post_save
    handler relies on the ``created=True`` branch instead.

    We use a pre_save + an attribute on ``instance`` (rather than
    querying again in post_save, or just checking
    ``not instance.trial_started``) so that:

      - ordinary landlord profile updates do NOT re-trigger the
        trial seed, and
      - an admin who explicitly revokes a trial with
        ``manage_trial revoke`` (which sets ``trial_started=False``
        and saves) is NOT immediately undone by the next save.

    One extra ``.only("role").get(pk=...)`` per update is cheap
    compared to the trial-seed transaction.
    """
    if instance.pk:
        try:
            instance._previous_role = (
                User.objects.only("role").get(pk=instance.pk).role
            )
        except User.DoesNotExist:
            instance._previous_role = None
    else:
        instance._previous_role = None


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == User.Role.TENANT:
            TenantProfile.objects.create(user=instance)
        elif instance.role == User.Role.LANDLORD:
            LandlordProfile.objects.create(user=instance)
            # Start a 1-month free trial the moment the landlord account
            # is created. ``start_landlord_trial`` is idempotent, so
            # even if the data migration has already seeded the trial
            # we won't double-write it. We don't wrap the profile
            # creation in the same atomic block because we want a
            # profile row even if the trial seed fails for any
            # reason (the trial can be backfilled later by an admin
            # running the seed management command).
            try:
                start_landlord_trial(instance)
            except Exception:
                logger.exception(
                    "create_user_profile: trial seed failed for landlord %s; "
                    "profile was created but the trial row is missing. "
                    "Run `python manage.py backfill_landlord_trials` to repair.",
                    instance.pk,
                )
    else:
        # Existing user being updated. If the role was just
        # changed TO landlord (i.e. a tenant was promoted, or the
        # user was created without a role and is now being assigned
        # landlord), seed the trial. We only fire on an actual
        # role transition (previous_role != landlord) so that:
        #   - ordinary landlord profile updates don't re-seed, and
        #   - ``manage_trial revoke`` (which clears trial_started
        #     but keeps role='landlord') is not immediately undone.
        # ``start_landlord_trial`` is still idempotent on its own,
        # so this branch is the same safety net.
        previous_role = getattr(instance, "_previous_role", None)
        if (
            instance.role == User.Role.LANDLORD
            and previous_role != User.Role.LANDLORD
        ):
            # A user changing roles may only have the profile for their old
            # role.  Create the new role's profile before any view tries to
            # access the reverse one-to-one relation.
            LandlordProfile.objects.get_or_create(user=instance)
            try:
                start_landlord_trial(instance)
            except Exception:
                logger.exception(
                    "create_user_profile: trial seed failed on role "
                    "change for landlord %s; "
                    "Run `python manage.py backfill_landlord_trials` to repair.",
                    instance.pk,
                )
        elif (
            instance.role == User.Role.TENANT
            and previous_role != User.Role.TENANT
        ):
            TenantProfile.objects.get_or_create(user=instance)
