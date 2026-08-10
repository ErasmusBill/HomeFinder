from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Region, District, Town, Area
from apps.common.cache import invalidate_locations_cache

@receiver([post_save, post_delete], sender=Region)
@receiver([post_save, post_delete], sender=District)
@receiver([post_save, post_delete], sender=Town)
@receiver([post_save, post_delete], sender=Area)
def location_cache_invalidation(sender, instance, **kwargs):
    invalidate_locations_cache()
