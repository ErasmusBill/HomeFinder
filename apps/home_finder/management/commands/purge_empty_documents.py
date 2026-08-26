"""
Delete LandlordDocument rows whose `file` field is an empty string.

Created to clean up rows left over from the Edit Property form bug where
a landlord could pick a document_type but submit without an actual file,
producing a row with file='' that later crashed templates rendering
{{ doc.file.url }}.

Usage:
    # Dry-run (default): list what would be deleted, do NOT delete.
    python manage.py purge_empty_documents

    # Actually delete them:
    python manage.py purge_empty_documents --delete

    # Also catch NULL file values (belt-and-suspenders):
    python manage.py purge_empty_documents --include-null --delete
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.core.cache import cache

from apps.home_finder.models import LandlordDocument
from apps.common.cache import (
    invalidate_documents_cache,
    invalidate_property_cache,
)


class Command(BaseCommand):
    help = "Delete LandlordDocument rows that have no file attached."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Actually perform the delete. Without this flag the command is a dry run.",
        )
        parser.add_argument(
            "--include-null",
            action="store_true",
            help="Also delete rows where file IS NULL (in addition to empty-string rows).",
        )

    def handle(self, *args, **options):
        do_delete = options["delete"]
        include_null = options["include_null"]

        qs = LandlordDocument.objects.all()
        if include_null:
            from django.db.models import Q
            qs = qs.filter(Q(file="") | Q(file__isnull=True))
        else:
            qs = qs.filter(file="")

        total = qs.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No empty-file LandlordDocument rows found. Nothing to do."))
            return

        # Show a preview so the operator can audit before deletion.
        self.stdout.write(self.style.WARNING(
            f"{'Will delete' if do_delete else '[DRY RUN] Would delete'} "
            f"{total} LandlordDocument row(s):"
        ))
        for doc in qs.order_by("-created_at")[:50]:
            self.stdout.write(
                f"  - id={doc.pk}  type={doc.document_type}  "
                f"status={doc.verification_status}  "
                f"landlord={doc.landlord_id}  property={doc.property_id}  "
                f"created={doc.created_at:%Y-%m-%d %H:%M}"
            )
        if total > 50:
            self.stdout.write(f"  ... and {total - 50} more (not shown)")

        if not do_delete:
            self.stdout.write(self.style.NOTICE(
                "\nThis was a DRY RUN. Re-run with --delete to actually remove these rows."
            ))
            return

        # Collect affected landlord + property ids so we can bust caches.
        affected_landlords = set(qs.values_list("landlord_id", flat=True))
        affected_properties = set(
            pid for pid in qs.values_list("property_id", flat=True) if pid is not None
        )

        with transaction.atomic():
            deleted_count, _ = qs.delete()

        # Invalidate caches so the next page load doesn't serve a stale
        # "this landlord has X docs" count from Redis.
        for landlord_id in affected_landlords:
            invalidate_documents_cache(landlord_id=landlord_id)
        for property_id in affected_properties:
            invalidate_property_cache(property_id=property_id)
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern("home_finder:documents:*")

        self.stdout.write(self.style.SUCCESS(
            f"\nDeleted {deleted_count} LandlordDocument row(s). "
            f"Caches invalidated for {len(affected_landlords)} landlord(s) "
            f"and {len(affected_properties)} property/ies."
        ))
