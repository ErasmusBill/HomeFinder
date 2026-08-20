import builtins
from django.db import models

from apps.account.models import User
from apps.common.models import BaseModel
from apps.home_finder.models import Area, District, Property, Region



class SavedProperty(BaseModel):
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_properties", limit_choices_to={"role": User.Role.TENANT})
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="saved_by")

    class Meta:
        unique_together = ("tenant", "property")

    def __str__(self):
        return f"{self.property}: {self.tenant.full_name}"


class PropertyView(BaseModel):
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="property_views")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="views")
    viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("tenant", "property")

    def __str__(self):
        return f"{self.property}: {self.tenant.full_name}"


class PropertyAlert(BaseModel):
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="property_alerts")
    region = models.ForeignKey(Region, on_delete=models.CASCADE)
    district = models.ForeignKey(District, on_delete=models.CASCADE, null=True, blank=True)
    area = models.ForeignKey(Area, on_delete=models.CASCADE, null=True, blank=True)
    min_price = models.DecimalField(max_digits=12, decimal_places=2)
    max_price = models.DecimalField(max_digits=12, decimal_places=2)
    room_type = models.CharField(max_length=30, choices=Property.RoomType.choices)
    is_active = models.BooleanField(default=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    notified_properties = models.ManyToManyField(
        "home_finder.Property",
        blank=True,
        related_name="notifying_property_alerts",
        help_text=(
            "Properties this alert has already been notified about. "
            "Used for per-(alert, property) dedup so the same property "
            "is never emailed to the same tenant twice."
        ),
    )

    def __str__(self):
        return f"Alert: {self.tenant.full_name} - {self.region}"


class ViewingRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="viewing_requests", null=True, blank=True)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="viewing_requests")
    
    # Guest requester fields (used when tenant is null)
    guest_name = models.CharField(max_length=255, blank=True, default="")
    guest_email = models.EmailField(max_length=255, blank=True, default="")
    guest_phone = models.CharField(max_length=30, blank=True, default="")

    preferred_date = models.DateField()
    preferred_time = models.TimeField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-created_at"]

    @builtins.property
    def is_guest(self):
        return self.tenant is None

    @builtins.property
    def requester_name(self):
        if self.tenant:
            return self.tenant.full_name or self.tenant.email
        return self.guest_name or "Guest"

    @builtins.property
    def requester_email(self):
        if self.tenant:
            return self.tenant.email
        return self.guest_email or ""

    @builtins.property
    def requester_phone(self):
        if self.tenant:
            return self.tenant.phone_number
        return self.guest_phone or ""

    def __str__(self):
        return f"{self.property}: {self.requester_name} ({self.status})"