from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.account.models import User
from apps.common.models import BaseModel


class Notification(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
    )
    title = models.CharField(max_length=120)
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)

    # Generic relation fields
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.CharField(max_length=255, null=True, blank=True)
    target = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
            models.Index(fields=['content_type', 'object_id']),
        ]
        verbose_name_plural = "Notifications"

    def __str__(self):
        status = "Read" if self.is_read else "Unread"
        return f"[{status}] {self.title} — {self.user.email}"
