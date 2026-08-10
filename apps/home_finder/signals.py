from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Property, PropertyMedia, Amenity, LandlordDocument
from .tasks import process_property_cover
from apps.common.cache import invalidate_property_cache, invalidate_amenities_cache, invalidate_documents_cache

@receiver(post_save, sender=Property)
def trigger_property_cover_processing(sender, instance, created, **kwargs):
    if created and instance.cover_image:
        # Fire the Celery background task asynchronously
        process_property_cover.delay(instance.pk)

@receiver([post_save, post_delete], sender=Property)
def property_cache_invalidation(sender, instance, **kwargs):
    invalidate_property_cache(instance)

@receiver([post_save, post_delete], sender=PropertyMedia)
def property_media_cache_invalidation(sender, instance, **kwargs):
    if instance.property_id:
        invalidate_property_cache(instance.property)

@receiver([post_save, post_delete], sender=Amenity)
def amenity_cache_invalidation(sender, instance, **kwargs):
    invalidate_amenities_cache()

@receiver([post_save, post_delete], sender=LandlordDocument)
def landlord_document_cache_invalidation(sender, instance, **kwargs):
    invalidate_documents_cache(landlord_id=instance.landlord_id, document_id=instance.pk)