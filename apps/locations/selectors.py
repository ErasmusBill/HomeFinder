from django.conf import settings
from django.core.cache import cache
from apps.locations.models import Region

CACHE_TTL = getattr(settings, 'CACHE_TTL', 300)

def location_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["properties", prefix, *[str(arg) for arg in args if arg is not None]])

def _invalidate_location_cache(location_obj=None):
    cache.delete(location_cache_key("locations"))

def get_all_locations():
    cache_key = location_cache_key("locations")
    locations = cache.get(cache_key)
    if locations is None:
        locations = list(
            Region.objects.prefetch_related(
                "districts__towns__areas"
            ).all()
        )
        cache.set(cache_key, locations, CACHE_TTL)
    return locations