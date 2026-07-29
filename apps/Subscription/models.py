from django.db import models
from apps.account.models import User
from apps.common.models import BaseModel

class SubscriptionPlan(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    duration_days = models.PositiveIntegerField(
        default=30,
        help_text="Duration of the plan in days (e.g., 30 for monthly)"
    )
    maximum_listings = models.PositiveIntegerField(
        default=5,
        help_text="Maximum number of active property listings allowed"
    )
    is_active = models.BooleanField(default=True, help_text="Whether this plan is currently available for purchase")

    class Meta:
        ordering = ["price"]
        verbose_name_plural = "Subscription Plans"

    def __str__(self):
        return f"{self.name} ({self.maximum_listings} Listings)"


class LandlordSubscription(BaseModel):
    landlord = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        limit_choices_to={"role": User.Role.LANDLORD},
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscribers")
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)


    idempotence_key = models.CharField(max_length=255, unique=True, blank=True, null=True)
    payment_reference = models.CharField(max_length=100, unique=True, blank=True, null=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name_plural = "Landlord Subscriptions"

    def __str__(self):
        return f"{self.landlord.full_name} - {self.plan.name} ({'Active' if self.is_active else 'Inactive'})"