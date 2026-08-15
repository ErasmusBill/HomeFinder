from django.db import models
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from apps.account.models import User
from apps.common.models import BaseModel
from apps.locations.models import Area, District, Region, Town


def generate_unique_slug(model_instance, source_field_value, slug_field_name="slug"):
    """Generates a unique slug by appending a short random string if a duplicate exists."""
    base_slug = slugify(source_field_value)
    if not base_slug:
        base_slug = "item"

    slug = base_slug
    ModelClass = model_instance.__class__

    # Exclude the current instance from the check if it's already saved
    query = ModelClass.objects.filter(**{slug_field_name: slug})
    if model_instance.pk:
        query = query.exclude(pk=model_instance.pk)

    while query.exists():
        random_suffix = get_random_string(length=5, allowed_chars="abcdefghijklmnopqrstuvwxyz0123456789")
        slug = f"{base_slug}-{random_suffix}"
        query = ModelClass.objects.filter(**{slug_field_name: slug})
        if model_instance.pk:
            query = query.exclude(pk=model_instance.pk)

    return slug


class Amenity(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Amenities"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_name = self.name

    def save(self, *args, **kwargs):
        if not self.slug or getattr(self, '_original_name', None) != self.name:
            self.slug = generate_unique_slug(self, self.name)
        super().save(*args, **kwargs)
        self._original_name = self.name

    def __str__(self):
        return self.name


class Property(BaseModel):

    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class RoomType(models.TextChoices):
        APARTMENT = "apartment", "Apartment"
        SELF_CONTAINED = "self_contained", "Self Contained"
        CHAMBER_AND_HALL = "chamber_and_hall", "Chamber & Hall"
        GUEST_HOUSE = "guest_house", "Guest House"

    class PaymentPeriod(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    landlord = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="properties",
        limit_choices_to={"role": User.Role.LANDLORD},
    )

    reference_number = models.CharField(max_length=30, unique=True, editable=False)
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    views_count = models.PositiveIntegerField(default=0)

    title = models.CharField(max_length=200)
    description = models.TextField()
    cover_image = models.ImageField(upload_to="properties/covers/")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    payment_period = models.CharField(max_length=20, choices=PaymentPeriod.choices, default=PaymentPeriod.MONTHLY)
    room_type = models.CharField(max_length=30, choices=RoomType.choices)
    verification_status = models.CharField(max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    publication_status = models.CharField(max_length=20, choices=PublicationStatus.choices, default=PublicationStatus.DRAFT)

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="properties")
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="properties")
    town = models.ForeignKey(Town, on_delete=models.PROTECT, related_name="properties")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="properties")

    amenities = models.ManyToManyField(Amenity, blank=True, related_name="properties")

    bedrooms = models.PositiveSmallIntegerField(default=1)
    bathrooms = models.PositiveSmallIntegerField(default=1)
    toilets = models.PositiveSmallIntegerField(default=1)
    parking_spaces = models.PositiveSmallIntegerField(default=0)
    floor_area = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, help_text="Area in square metres (m²)")

    is_furnished = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)

    available_from = models.DateField(blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Properties"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_title = getattr(self, 'title', None)

    def generate_reference_number(self):
        """Generates a unique reference number for the property (e.g., HF-ABC123XY)."""
        while True:
            random_str = get_random_string(length=8, allowed_chars="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
            ref_num = f"HF-{random_str}"
            if not Property.objects.filter(reference_number=ref_num).exists():
                return ref_num

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self.generate_reference_number()

        if not self.slug or getattr(self, '_original_title', None) != self.title:
            self.slug = generate_unique_slug(self, self.title)

        try:
            super().save(*args, **kwargs)
        except models.deletion.IntegrityError as e:
            if 'reference_number' in str(e):
                self.reference_number = self.generate_reference_number()
                super().save(*args, **kwargs)
            else:
                raise
        self._original_title = self.title

    def __str__(self):
        return f"{self.title} (Landlord: {self.landlord.full_name})"


class PropertyMedia(BaseModel):

    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        DOCUMENT = "document", "Document"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="media")
    file = models.FileField(upload_to="properties/media/")
    media_type = models.CharField(max_length=20, choices=MediaType.choices, default=MediaType.IMAGE)
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    caption = models.CharField(max_length=200, blank=True)
    thumbnail = models.ImageField(upload_to="properties/thumbnails/", blank=True, null=True)
    blurhash = models.CharField(max_length=100, blank=True, null=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_public = models.BooleanField(default=True)
    is_processed = models.BooleanField(default=False, help_text="Whether the file has been processed (compressed, resized, etc.).")

    class Meta:
        ordering = ["order", "created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            source_string = f"{self.property.title}-{self.media_type}-{self.order}"
            self.slug = generate_unique_slug(self, source_string)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_media_type_display()} - {self.property.title}"


class PropertyInterest(BaseModel):
    """A tenant's saved expression of interest in a property."""

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="interests",
    )
    tenant = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="property_interests",
        limit_choices_to={"role": User.Role.TENANT},
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "tenant"],
                name="unique_tenant_property_interest",
            ),
        ]
        verbose_name_plural = "Property interests"

    def __str__(self):
        return f"{self.tenant.full_name} is interested in {self.property.title}"

class LandlordDocument(BaseModel):

    class DocumentType(models.TextChoices):
        NATIONAL_ID = "national_id", "National ID / Ghana Card"
        BUSINESS_REGISTRATION = "business_registration", "Business Registration Certificate"
        PROOF_OF_ADDRESS = "proof_of_address", "Proof of Address"
        PROPERTY_OWNERSHIP = "property_ownership", "Proof of Property Ownership"
        OTHER = "other", "Other"

    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    landlord = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="documents",
        limit_choices_to={"role": User.Role.LANDLORD},
    )
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    file = models.FileField(upload_to="landlords/documents/")

    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="landlord_documents",
        null=True, blank=True,
    )

    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True, help_text="For documents with an expiry, e.g. licenses.")

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Landlord Documents"

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.landlord.full_name} ({self.verification_status})"
