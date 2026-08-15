from django.contrib import admin

from apps.tenant.models import PropertyAlert, PropertyView, SavedProperty, ViewingRequest


@admin.register(SavedProperty)
class SavedPropertyAdmin(admin.ModelAdmin):
    list_display = ("tenant", "property", "created_at")
    list_filter = ("created_at",)
    search_fields = ("tenant__full_name", "tenant__email", "property__title")
    autocomplete_fields = ("tenant", "property")


@admin.register(PropertyView)
class PropertyViewAdmin(admin.ModelAdmin):
    list_display = ("tenant", "property", "viewed_at")
    list_filter = ("viewed_at",)
    search_fields = ("tenant__full_name", "tenant__email", "property__title")
    autocomplete_fields = ("tenant", "property")


@admin.register(PropertyAlert)
class PropertyAlertAdmin(admin.ModelAdmin):
    list_display = ("tenant", "region", "district", "area", "min_price", "max_price", "room_type", "is_active")
    list_filter = ("is_active", "room_type", "region")
    search_fields = ("tenant__full_name", "tenant__email")
    autocomplete_fields = ("tenant", "region", "district", "area")


@admin.register(ViewingRequest)
class ViewingRequestAdmin(admin.ModelAdmin):
    list_display = ("tenant", "property", "preferred_date", "preferred_time", "status", "created_at")
    list_filter = ("status", "preferred_date")
    search_fields = ("tenant__full_name", "tenant__email", "property__title")
    autocomplete_fields = ("tenant", "property")