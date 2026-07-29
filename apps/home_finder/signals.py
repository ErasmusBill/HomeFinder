from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Property
from .tasks import process_property_cover

@receiver(post_save, sender=Property)
def trigger_property_cover_processing(sender, instance, created, **kwargs):
    if created and instance.cover_image:
        # Fire the Celery background task asynchronously
        process_property_cover.delay(instance.pk)