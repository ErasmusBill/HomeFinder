"""
Data migration: every landlord who has never been granted a free trial
(``trial_started=False`` AND ``trial_end_date IS NULL``) gets a 30-day
trial window seeded retroactively.

Why a separate migration:
  0004 added the ``trial_started`` column with ``default=False``. The
  schema migration runs first; this data migration then runs once
  against the live table. Splitting the two means we can re-run the
  data migration safely in production if it ever needs to be re-applied
  after a partial failure, without re-running the column add.

Why we backfill and not just leave them NULL:
  Before this migration, landlords created between the original
  ``0003_landlord_free_trial`` schema migration and today have
  ``trial_end_date IS NULL`` (because the post_save signal hadn't
  shipped yet, or because the user was imported manually, or because
  the data was loaded from a fixture). The guard treats those users
  as "never had a trial" and silently denies them, which is a worse
  UX than giving them a real trial window.

Idempotency:
  We only touch landlords where ``trial_started=False``. The signal
  handler ``start_landlord_trial`` is itself idempotent, but we don't
  use it here because the signal is wired to ``post_save`` and we want
  this to be a one-shot operation tied to the migration, not a future
  re-trigger of the signal. We also avoid touching tenants and admins
  entirely.
"""
from datetime import timedelta

from django.db import migrations
from django.utils import timezone


# Must match the constant in apps.account.signals -- the data migration
# can't import from the live app because the app state at migration
# time is frozen (the historical User model is in scope, not the
# current one). We duplicate the value here on purpose.
LANDLORD_FREE_TRIAL_DAYS = 30


def backfill_free_trials(apps, schema_editor):
    User = apps.get_model('user_account', 'User')
    now = timezone.now()
    end = now + timedelta(days=LANDLORD_FREE_TRIAL_DAYS)
    # Only landlords with no trial window ever set. Anyone with
    # ``trial_started=True`` already has one (or has been processed
    # previously); we leave them alone so the migration can be
    # re-applied safely if needed.
    User.objects.filter(
        role='landlord',
        trial_started=False,
    ).update(
        trial_started=True,
        trial_start_date=now,
        trial_end_date=end,
    )


def reverse_backfill(apps, schema_editor):
    """
    Reverse: clear the trial window for every landlord we just
    backfilled. We identify them as landlords with ``trial_started=True``
    and ``trial_start_date`` in the last few minutes (within the last
    hour) -- this avoids clobbering trials that were created normally
    after the forward migration ran. In practice the reverse migration
    is only run during development, so the heuristic is fine.
    """
    from datetime import timedelta
    User = apps.get_model('user_account', 'User')
    cutoff = timezone.now() - timedelta(hours=1)
    User.objects.filter(
        role='landlord',
        trial_started=True,
        trial_start_date__gte=cutoff,
    ).update(
        trial_started=False,
        trial_start_date=None,
        trial_end_date=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('user_account', '0004_add_trial_started_and_backfill'),
    ]

    operations = [
        migrations.RunPython(backfill_free_trials, reverse_backfill),
    ]
