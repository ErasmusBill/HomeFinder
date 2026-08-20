from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import Property, PropertyMedia, Amenity, LandlordDocument
from .tasks import process_property_cover
from apps.common.cache import invalidate_property_cache, invalidate_amenities_cache, invalidate_documents_cache

@receiver(post_save, sender=Property)
def trigger_property_cover_processing(sender, instance, created, **kwargs):
    if created and instance.cover_image:
        def _enqueue_cover():
            process_property_cover.delay(str(instance.pk))
        transaction.on_commit(_enqueue_cover)



@receiver(post_save, sender=Property)
def trigger_property_alert_matching(sender, instance, created, **kwargs):
    """
    On Property creation, queue a matcher task for the new listing.
    The matcher itself is gated on ``settings.PROPERTY_ALERTS_ENABLED``,
    so flipping that flag to ``False`` is a complete kill switch for
    this signal — no further configuration needed.

    We use ``transaction.on_commit`` so the Celery task only fires once
    the property row is durably committed; otherwise a task picked up
    immediately could try to read a row the DB hasn't seen yet. This
    mirrors the pattern in ``apps/Subscription/tasks.py``.

    The matcher's own ``is_property_alertable`` filter (publication
    status, availability) handles the case where a landlord created a
    draft and only later published it — for that path the hourly
    ``property_alert_catchup_task`` in ``apps/tenant/tasks.py`` is the
    safety net.
    """
    if not created:
        return

    def _enqueue():
        from apps.tenant.tasks import match_and_dispatch_property_alerts_task
        match_and_dispatch_property_alerts_task.delay(str(instance.pk))

    transaction.on_commit(_enqueue)

@receiver([post_save, post_delete], sender=Property)
def property_cache_invalidation(sender, instance, **kwargs):
    invalidate_property_cache(instance)

@receiver([post_save, post_delete], sender=PropertyMedia)
def property_media_cache_invalidation(sender, instance, **kwargs):
    if instance.property_id:
        invalidate_property_cache(property_id=instance.property_id)

@receiver([post_save, post_delete], sender=Amenity)
def amenity_cache_invalidation(sender, instance, **kwargs):
    invalidate_amenities_cache()

@receiver([post_save, post_delete], sender=LandlordDocument)
def landlord_document_cache_invalidation(sender, instance, **kwargs):
    if instance.property_id:
        invalidate_property_cache(property_id=instance.property_id)
    invalidate_documents_cache(landlord_id=instance.landlord_id, document_id=instance.pk)