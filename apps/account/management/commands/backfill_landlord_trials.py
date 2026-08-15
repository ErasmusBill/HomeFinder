"""
``python manage.py backfill_landlord_trials`` — repair command for
landlords whose trial row is missing.

The post_save signal ``create_user_profile`` creates a profile and
attempts to seed a trial the moment a landlord is created. If the
trial seed fails for any reason (transient DB error, race, partial
deploy) the profile row exists but ``trial_started`` stays False.

This command finds every landlord in that broken state and seeds
the trial for them. Idempotent: re-running is a no-op.

This is *not* a replacement for the original data migration in
``apps/account/migrations/0005_backfill_landlord_free_trials.py``,
which was a one-shot at the time the trial column was added. This
command exists for the ongoing "trial row went missing" repair
case that the new error-handling in ``signals.py`` logs about.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.account.models import User
from apps.account.signals import start_landlord_trial


class Command(BaseCommand):
    help = "Seed a 30-day free trial for any landlord missing one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be changed without writing.",
        )

    def handle(self, *args, **options):
        # Match the exact "broken" state: landlord exists, but the
        # trial seed never landed. We intentionally do NOT include
        # landlords whose trial has already expired (they had one
        # once, the row is intact) — those are fine.
        queryset = User.objects.filter(
            role=User.Role.LANDLORD,
            trial_started=False,
        )

        candidates = list(queryset.values_list("pk", "email"))
        if not candidates:
            self.stdout.write(self.style.SUCCESS(
                "No landlords are missing a trial. Nothing to do."
            ))
            return

        self.stdout.write(f"Found {len(candidates)} landlord(s) missing a trial.")
        if options["dry_run"]:
            for pk, email in candidates:
                self.stdout.write(f"  would seed: pk={pk} email={email}")
            return

        repaired = 0
        for pk, _email in candidates:
            try:
                with transaction.atomic():
                    landlord = User.objects.get(pk=pk)
                    if start_landlord_trial(landlord):
                        repaired += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f"  failed for pk={pk}: {exc}"
                ))

        self.stdout.write(self.style.SUCCESS(
            f"Repaired {repaired} of {len(candidates)} landlord(s)."
        ))
