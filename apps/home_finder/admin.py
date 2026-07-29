from django.contrib import admin
from .models import Amenity, Property, PropertyMedia


class PropertyMediaInline(admin.TabularInline):
    model = PropertyMedia
    extra = 1
    fields = ("file", "media_type", "caption", "order", "is_public", "is_processed")


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        "reference_number",
        "title",
        "room_type",
        "price",
        "payment_period",
        "verification_status",
        "publication_status",
        "is_available",
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
    search_fields = ("title", "reference_number", "description", "town__name", "area__name")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ["region", "district", "town", "area"]
    filter_horizontal = ("amenities",)
    inlines = [PropertyMediaInline]

    readonly_fields = ("reference_number", "created_at", "updated_at")


@admin.register(PropertyMedia)
class PropertyMediaAdmin(admin.ModelAdmin):
    list_display = ("property", "media_type", "order", "is_public", "is_processed", "created_at")
    list_filter = ("media_type", "is_public", "is_processed")
    search_fields = ("property__title", "caption")