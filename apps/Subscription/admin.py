from django.contrib import admin
from django.utils import timezone

from .models import SubscriptionPlan, LandlordSubscription


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "price",
        "duration_days",
        "maximum_listings",
        "is_active",
    )
    list_filter = (
        "is_active",
        "duration_days",
    )
    search_fields = (
        "name",
        "description",
    )
    ordering = ("price",)
    list_editable = ("is_active",)
    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(LandlordSubscription)
class LandlordSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "landlord",
        "plan",
        "status",
        "start_date",
        "end_date",
        "days_remaining",
        "expired",
        "is_active",
    )
    list_filter = (
        "status",
        "is_active",
        "plan",
    )
    search_fields = (
        "landlord__full_name",
        "landlord__email",
        "payment_reference",
    )
    autocomplete_fields = (
        "landlord",
        "plan",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "start_date",
        "end_date",
        "days_remaining",
        "expired",
    )

    @admin.display(description="Days Left")
    def days_remaining(self, obj):
        """
        Pending subscriptions (not yet paid) have no end_date, so guard
        against None before doing datetime arithmetic.
        """
        if not obj.end_date:
            return "—"
        remaining = (obj.end_date - timezone.now()).days
        return max(remaining, 0)

    @admin.display(boolean=True, description="Expired")
    def expired(self, obj):
        if not obj.end_date:
            return False
        return obj.end_date < timezone.now()