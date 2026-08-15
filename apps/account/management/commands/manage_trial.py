"""
``python manage.py manage_trial`` — per-landlord trial administration.

Operations:

  * ``status`` (default) — print the trial state of one or all landlords
    so support can answer "when does my trial end?" without poking the
    Django admin.
  * ``extend`` — push the trial ``end_date`` out by N days from now.
    Use this when a landlord asks for a few extra days in writing.
  * ``reset`` — clear ``trial_started`` and re-seed a fresh 30-day
    window. Use this for "I never had a trial" support escalations
    (e.g. the original signal failed at signup and backfill was missed).
  * ``revoke`` — zero out the trial window so the landlord is treated
    as "never had a trial" again. Use sparingly — there's no audit
    log here, so this is the "I really mean it" command.

Examples:

  # Status of one landlord
  python manage.py manage_trial --email landlord@example.com

  # Status of every landlord
  python manage.py manage_trial

  # Give a landlord 14 more days
  python manage.py manage_trial --email landlord@example.com extend --days 14

  # Re-seed a fresh 30-day window
  python manage.py manage_trial --email landlord@example.com reset

  # Revoke the trial entirely
  python manage.py manage_trial --email landlord@example.com revoke
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.account.models import User
from apps.account.signals import (
    LANDLORD_FREE_TRIAL_DAYS,
    start_landlord_trial,
)


def _resolve_landlord(*, email, pk):
    """
    Look up a single landlord by email or pk. Raises CommandError with
    a friendly message instead of leaking a Django DoesNotExist traceback
    to support staff running this by hand.
    """
    qs = User.objects.filter(role=User.Role.LANDLORD)
    if pk is not None:
        landlord = qs.filter(pk=pk).first()
        if landlord is None:
            raise CommandError(f"No landlord found with pk={pk}.")
        return landlord
    if email is None:
        raise CommandError(
            "Pass --email <addr> or --pk <id> to pick a landlord."
        )
    landlord = qs.filter(email__iexact=email).first()
    if landlord is None:
        raise CommandError(f"No landlord found with email={email!r}.")
    return landlord


def _format_status(landlord, now):
    """
    Render a single landlord's trial state in a way that's readable in
    a terminal — used by both the default action and the per-command
    "before / after" printouts so support can confirm what changed.
    """
    if not landlord.trial_started:
        return (
            f"  trial_started: False (no trial row)\n"
            f"  is_trial_active: False"
        )

    remaining = ""
    if landlord.trial_end_date and landlord.trial_end_date > now:
        delta = landlord.trial_end_date - now
        # Match the model's ceiling math for honesty.
        import math
        days = max(0, math.ceil(delta.total_seconds() / 86400))
        remaining = f"  days_remaining: {days}\n"
    elif landlord.trial_end_date and landlord.trial_end_date <= now:
        remaining = "  days_remaining: 0 (expired)\n"

    notified = (
        landlord.notified_trial_ended_at.isoformat()
        if landlord.notified_trial_ended_at
        else "None"
    )
    return (
        f"  trial_started: True\n"
        f"  trial_start_date: {landlord.trial_start_date.isoformat() if landlord.trial_start_date else 'None'}\n"
        f"  trial_end_date: {landlord.trial_end_date.isoformat() if landlord.trial_end_date else 'None'}\n"
        f"{remaining}"
        f"  is_trial_active: {landlord.is_trial_active}\n"
        f"  is_trial_expired: {landlord.is_trial_expired}\n"
        f"  notified_trial_ended_at: {notified}"
    )


class Command(BaseCommand):
    help = "Inspect and administer landlord free-trial windows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=None,
            help="Landlord email (case-insensitive). Required for extend/reset/revoke.",
        )
        parser.add_argument(
            "--pk",
            default=None,
            help="Landlord primary key (string; this project uses UUID PKs). "
                 "Alternative to --email.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Apply to every landlord (status only).",
        )

        sub = parser.add_subparsers(dest="action", required=False)

        # status (no extra args)
        sub.add_parser("status", help="Show trial state (default action).")

        extend = sub.add_parser("extend", help="Push trial end_date out by N days.")
        extend.add_argument(
            "--days",
            type=int,
            required=True,
            help="Number of days to add to the current trial end_date.",
        )

        sub.add_parser(
            "reset",
            help="Clear and re-seed a fresh 30-day trial window.",
        )

        sub.add_parser(
            "revoke",
            help="Zero out the trial so the landlord is treated as never-trial.",
        )

    def handle(self, *args, **options):
        action = options.get("action") or "status"

        # Default status (no --all, no --email, no --pk) is a no-op;
        # require an explicit target to avoid printing hundreds of rows
        # by accident in production.
        if action == "status":
            if options["all"]:
                self._status_all()
            else:
                landlord = _resolve_landlord(
                    email=options["email"], pk=options["pk"]
                )
                self._status_one(landlord)
            return

        # All other actions mutate a single landlord.
        landlord = _resolve_landlord(
            email=options["email"], pk=options["pk"]
        )
        self.stdout.write("Before:")
        self.stdout.write(_format_status(landlord, timezone.now()))

        if action == "extend":
            self._extend(landlord, days=options["days"])
        elif action == "reset":
            self._reset(landlord)
        elif action == "revoke":
            self._revoke(landlord)
        else:
            raise CommandError(f"Unknown action: {action!r}")

        landlord.refresh_from_db()
        self.stdout.write("After:")
        self.stdout.write(_format_status(landlord, timezone.now()))

    # ------------------------------------------------------------------
    # Read-only actions
    # ------------------------------------------------------------------

    def _status_one(self, landlord):
        self.stdout.write(
            f"Landlord pk={landlord.pk} email={landlord.email} "
            f"name={landlord.full_name!r}"
        )
        self.stdout.write(_format_status(landlord, timezone.now()))

    def _status_all(self):
        now = timezone.now()
        landlords = User.objects.filter(role=User.Role.LANDLORD).order_by("pk")
        count = landlords.count()
        if count == 0:
            self.stdout.write("No landlords in the system.")
            return
        self.stdout.write(f"{count} landlord(s):")
        for landlord in landlords:
            tag = (
                "active " if landlord.is_trial_active
                else "expired" if landlord.is_trial_expired
                else "never  "
            )
            end = (
                landlord.trial_end_date.date().isoformat()
                if landlord.trial_end_date else "—"
            )
            self.stdout.write(
                f"  [{tag}] pk={landlord.pk} "
                f"email={landlord.email:<40} trial_end={end}"
            )

    # ------------------------------------------------------------------
    # Mutating actions
    # ------------------------------------------------------------------

    def _extend(self, landlord, *, days):
        if days <= 0:
            raise CommandError("--days must be a positive integer.")
        if not landlord.trial_started or landlord.trial_end_date is None:
            raise CommandError(
                "This landlord has no trial to extend. Use `reset` to "
                "seed a fresh 30-day window, or `revoke`/`reset` first."
            )
        with transaction.atomic():
            locked = (
                User.objects.select_for_update().get(pk=landlord.pk)
            )
            # Extend from whichever is later: the existing end_date or
            # now. This way, calling extend on an already-expired trial
            # gives a fresh window of N days from today, rather than
            # leaving the end_date in the past.
            new_end = max(locked.trial_end_date, timezone.now()) + timedelta(days=days)
            locked.trial_end_date = new_end
            # If the trial had been marked "notified as ended", the
            # landlord is about to get their window back — clear the
            # flag so the daily beat task can re-notify them if/when
            # this new window eventually ends.
            locked.notified_trial_ended_at = None
            locked.save(update_fields=[
                "trial_end_date", "notified_trial_ended_at",
            ])
        self.stdout.write(self.style.SUCCESS(
            f"Extended trial for pk={landlord.pk} by {days} day(s). "
            f"New end_date: {new_end.isoformat()}"
        ))

    def _reset(self, landlord):
        # ``start_landlord_trial`` is idempotent — it refuses to run
        # when trial_started is already True. So we explicitly clear
        # the flag first to force a re-seed. The function itself
        # re-acquires a row lock so this is concurrency-safe.
        with transaction.atomic():
            User.objects.filter(pk=landlord.pk).update(
                trial_started=False,
                trial_start_date=None,
                trial_end_date=None,
            )
            refreshed = User.objects.get(pk=landlord.pk)
            started = start_landlord_trial(refreshed)
        if not started:
            # The function only returns False for non-landlords or
            # already-seeded trials. We just cleared the flag, so
            # "already-seeded" shouldn't be reachable; surface this
            # as an error so support can investigate.
            raise CommandError(
                "Reset failed: start_landlord_trial refused to run. "
                "Check that the user is still a landlord."
            )
        self.stdout.write(self.style.SUCCESS(
            f"Re-seeded a {LANDLORD_FREE_TRIAL_DAYS}-day trial for "
            f"pk={landlord.pk}."
        ))

    def _revoke(self, landlord):
        with transaction.atomic():
            User.objects.filter(pk=landlord.pk).update(
                trial_started=False,
                trial_start_date=None,
                trial_end_date=None,
                notified_trial_ended_at=None,
            )
        self.stdout.write(self.style.WARNING(
            f"Revoked trial for pk={landlord.pk}. They will be treated "
            f"as never-had-a-trial going forward."
        ))
