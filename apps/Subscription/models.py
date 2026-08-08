from django.db import models
from django.utils import timezone
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
    is_free = models.BooleanField(default=False)

    class Meta:
        ordering = ["price"]
        verbose_name_plural = "Subscription Plans"

    def __str__(self):
        return f"{self.name} ({self.maximum_listings} Listings)"


class LandlordSubscription(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'

    landlord = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        limit_choices_to={"role": User.Role.LANDLORD},
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscribers")
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    is_active = models.BooleanField(default=False)
    idempotence_key = models.CharField(max_length=255, unique=True, blank=True, null=True)
    payment_reference = models.CharField(max_length=100, unique=True, blank=True, null=True)

    # --- new fields for cancellation / scheduled downgrade ---
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(
        default=False,
        help_text="If True, subscription will not renew and access ends at end_date."
    )
    pending_plan = models.ForeignKey(
        SubscriptionPlan, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Scheduled downgrade target, applied automatically at end_date."
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Landlord Subscriptions"

    def __str__(self):
        return f"{self.landlord.full_name} - {self.plan.name} ({self.status})"

    @property
    def is_expired(self):
        return bool(self.end_date and self.end_date < timezone.now())

    @property
    def is_currently_active(self):
        return self.status == self.Status.SUCCESS and self.is_active and not self.is_expired

    def activate(self):
        """Call only once payment is confirmed (webhook or verified callback)."""
        now = timezone.now()
        self.start_date = now
        self.end_date = now + timezone.timedelta(days=self.plan.duration_days)
        self.status = self.Status.SUCCESS
        self.is_active = True
        self.save(update_fields=['start_date', 'end_date', 'status', 'is_active'])

    def cancel(self, immediate=False):
        """
        Cancel this subscription. By default, cancels at period end — the
        landlord keeps access until end_date, then it lapses. immediate=True
        cuts access off right away (support/admin use).
        """
        self.cancelled_at = timezone.now()
        if immediate:
            self.is_active = False
            self.end_date = timezone.now()
        else:
            self.cancel_at_period_end = True
        self.save(update_fields=['cancelled_at', 'is_active', 'end_date', 'cancel_at_period_end'])

    def reactivate(self):
        """Undo a scheduled (not-yet-effective) cancellation."""
        if self.is_expired:
            raise ValueError("Cannot reactivate an expired subscription.")
        self.cancelled_at = None
        self.cancel_at_period_end = False
        self.save(update_fields=['cancelled_at', 'cancel_at_period_end'])

    def schedule_plan_change(self, new_plan):
        """Schedule a downgrade — applied automatically when this period ends."""
        self.pending_plan = new_plan
        self.save(update_fields=['pending_plan'])