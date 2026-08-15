from django.contrib import admin
from .models import Amenity, LandlordDocument, Property, PropertyInterest, PropertyMedia


class PropertyMediaInline(admin.TabularInline):
    model = PropertyMedia
    extra = 1
    readonly_fields = ("slug", "is_processed")
    fields = ("media_type", "file", "thumbnail", "caption", "order", "is_public", "is_processed", "slug")


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("slug", "created_at", "updated_at")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        "reference_number",
        "title",
        "landlord",
        "price",
        "payment_period",
        "room_type",
        "verification_status",
        "publication_status",
        "is_available",
        "views_count",
    )
    list_filter = (
        "verification_status",
        "publication_status",
        "room_type",
        "payment_period",
        "is_furnished",
        "is_available",
        "region",
    )
    search_fields = (
        "title",
        "reference_number",
        "description",
        "landlord__email",
        "landlord__full_name",
        "town__name",
        "area__name",
    )
    readonly_fields = (
        "reference_number",
        "slug",
        "views_count",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("landlord", "region", "district", "town", "area")
    filter_horizontal = ("amenities",)
    inlines = [PropertyMediaInline]

    fieldsets = (
        ("Basic Information", {
            "fields": ("reference_number", "slug", "title", "description", "landlord", "cover_image")
        }),
        ("Pricing & Classification", {
            "fields": ("price", "payment_period", "room_type", "is_furnished", "amenities")
        }),
        ("Location Details", {
            "fields": ("region", "district", "town", "area", "latitude", "longitude")
        }),
        ("Property Specifications", {
            "fields": ("bedrooms", "bathrooms", "toilets", "parking_spaces", "floor_area")
        }),
        ("Status & Availability", {
            "fields": ("verification_status", "publication_status", "is_available", "available_from", "views_count")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(PropertyMedia)
class PropertyMediaAdmin(admin.ModelAdmin):
    list_display = ("property", "media_type", "order", "is_public", "is_processed", "created_at")
    list_filter = ("media_type", "is_public", "is_processed")
    search_fields = ("property__title", "property__reference_number", "caption")
    readonly_fields = ("slug", "created_at", "updated_at")
    autocomplete_fields = ("property",)


@admin.register(PropertyInterest)
class PropertyInterestAdmin(admin.ModelAdmin):
    list_display = ("tenant", "property", "created_at")
    search_fields = ("tenant__full_name", "tenant__email", "property__title", "property__reference_number")
    autocomplete_fields = ("tenant", "property")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LandlordDocument)
class LandlordDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "landlord",
        "document_type",
        "property",
        "verification_status",
        "expires_at",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("verification_status", "document_type")
    search_fields = (
        "landlord__email",
        "landlord__full_name",
        "property__title",
        "property__reference_number",
    )
    readonly_fields = ("reviewed_at", "created_at", "updated_at")
    autocomplete_fields = ("landlord", "property", "reviewed_by")

    fieldsets = (
        ("Document Details", {
            "fields": ("landlord", "document_type", "file", "property", "expires_at")
        }),
        ("Verification & Review", {
            "fields": ("verification_status", "rejection_reason", "reviewed_by", "reviewed_at")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
