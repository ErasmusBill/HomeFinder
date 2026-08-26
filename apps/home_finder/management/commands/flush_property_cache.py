"""
Flush all property-related cache keys.

Use this whenever the homepage "Featured Properties" section or the
property-detail page is serving stale / empty results in production but
the data is clearly present in the database. This is usually caused by
the 1-minute featured cache or the per-slug detail cache holding an
empty result from a moment when the underlying query returned nothing.

Usage:
    python manage.py flush_property_cache            # property keys only (safe)
    python manage.py flush_property_cache --all      # wipe the entire Redis cache
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache

from apps.common.cache import invalidate_property_cache


PROPERTY_KEY_PATTERNS = [
    "properties:*",
    "home_finder:properties:*",
    "home_featured_*_epoch_*",
]


class Command(BaseCommand):
    help = "Flush property-related cache entries (or the entire Redis cache with --all)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Wipe the ENTIRE Redis cache, not just property keys.",
        )

    def handle(self, *args, **options):
        if options["all"]:
            cache.clear()
            self.stdout.write(self.style.SUCCESS("Cleared the entire cache."))
            return

        cleared_any = False

        # django-redis exposes delete_pattern; fall back to invalidator
        # helper which knows the standard key prefixes we use.
        if hasattr(cache, "delete_pattern"):
            for pattern in PROPERTY_KEY_PATTERNS:
                try:
                    cache.delete_pattern(pattern)
                    self.stdout.write(f"  deleted pattern: {pattern}")
                    cleared_any = True
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f"  could not delete pattern {pattern}: {e}"
                    ))
        else:
            # Fallback path: use the shared invalidator (also covers
            # the explicit keys it knows about).
            invalidate_property_cache()
            self.stdout.write("  ran invalidate_property_cache() fallback.")
            cleared_any = True

        if cleared_any:
            self.stdout.write(self.style.SUCCESS(
                "Property cache flushed. Reload the homepage and detail pages now."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "No cache backend supported pattern deletion and the fallback "
                "did nothing. Re-run with --all to wipe the entire cache."
            ))
