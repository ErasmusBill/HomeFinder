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

    def __str__(self):
        return f"Alert: {self.tenant.full_name} - {self.region}"


class ViewingRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="viewing_requests")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="viewing_requests")
    preferred_date = models.DateField()
    preferred_time = models.TimeField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    def __str__(self):
        return f"{self.property}: {self.tenant.full_name} ({self.status})"