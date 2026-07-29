from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, TenantProfile, LandlordProfile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == User.Role.TENANT:
            TenantProfile.objects.create(user=instance)
        elif instance.role == User.Role.LANDLORD:
            LandlordProfile.objects.create(user=instance)
