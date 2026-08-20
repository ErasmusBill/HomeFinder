from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import SubscriptionPlan
from apps.common.cache import invalidate_subscription_plans_cache


@receiver([post_save, post_delete], sender=SubscriptionPlan)
def trigger_invalidate_subscription_plans_cache(sender, **kwargs):
    """
    Clear the plans list cache whenever a SubscriptionPlan is created,
    updated or deleted so the pricing page always reflects reality.
    """
    invalidate_subscription_plans_cache()
