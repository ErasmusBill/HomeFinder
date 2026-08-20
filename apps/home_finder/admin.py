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


    actions = ["verify_properties", "reject_properties"]

    @admin.action(description="Verify and approve selected properties")
    def verify_properties(self, request, queryset):
        from apps.landloards.tasks import notify_landlord_property_verified_task
        from apps.common.cache import invalidate_property_cache
        from django.db import transaction

        count = 0
        for prop in queryset:
            old_status = prop.verification_status
            if old_status != Property.VerificationStatus.VERIFIED:
                prop.verification_status = Property.VerificationStatus.VERIFIED
                prop.save(update_fields=["verification_status"])
                invalidate_property_cache(prop)
                prop_id = str(prop.pk)
                transaction.on_commit(lambda p_id=prop_id, o_st=old_status: notify_landlord_property_verified_task.delay(p_id, previous_status=o_st))
                count += 1
        self.message_user(request, f"{count} property listing(s) verified and landlord(s) notified.")

    @admin.action(description="Reject selected properties")
    def reject_properties(self, request, queryset):
        from apps.landloards.tasks import notify_landlord_property_verified_task
        from apps.common.cache import invalidate_property_cache
        from django.db import transaction

        count = 0
        for prop in queryset:
            old_status = prop.verification_status
            if old_status != Property.VerificationStatus.REJECTED:
                prop.verification_status = Property.VerificationStatus.REJECTED
                prop.save(update_fields=["verification_status"])
                invalidate_property_cache(prop)
                prop_id = str(prop.pk)
                transaction.on_commit(lambda p_id=prop_id, o_st=old_status: notify_landlord_property_verified_task.delay(p_id, previous_status=o_st))
                count += 1
        self.message_user(request, f"{count} property listing(s) rejected and landlord(s) notified.")

    def save_model(self, request, obj, form, change):
        from django.db import transaction
        from apps.landloards.tasks import notify_landlord_property_verified_task

        old_status = form.initial.get("verification_status") if change else None
        super().save_model(request, obj, form, change)
        if change and "verification_status" in form.changed_data:
            prop_id = str(obj.pk)
            transaction.on_commit(lambda: notify_landlord_property_verified_task.delay(prop_id, previous_status=old_status))


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

    actions = ["verify_documents", "reject_documents"]

    @admin.action(description="Approve and verify selected documents")
    def verify_documents(self, request, queryset):
        from apps.landloards.tasks import notify_landlord_document_reviewed_task
        from apps.common.cache import invalidate_property_cache, invalidate_documents_cache
        from django.db import transaction
        from django.utils import timezone

        count = 0
        for doc in queryset:
            old_status = doc.verification_status
            if old_status != LandlordDocument.VerificationStatus.VERIFIED:
                doc.verification_status = LandlordDocument.VerificationStatus.VERIFIED
                doc.reviewed_by = request.user
                doc.reviewed_at = timezone.now()
                doc.rejection_reason = ""
                doc.save(update_fields=["verification_status", "reviewed_by", "reviewed_at", "rejection_reason"])
                invalidate_documents_cache(landlord_id=doc.landlord_id, document_id=doc.pk)
                if doc.property_id:
                    invalidate_property_cache(property_id=doc.property_id)
                else:
                    invalidate_property_cache(landlord_id=doc.landlord_id)
                doc_id = str(doc.pk)
                transaction.on_commit(lambda d_id=doc_id, o_st=old_status: notify_landlord_document_reviewed_task.delay(d_id, previous_status=o_st))
                count += 1
        self.message_user(request, f"{count} document(s) verified and landlord(s) notified.")

    @admin.action(description="Reject selected documents")
    def reject_documents(self, request, queryset):
        from apps.landloards.tasks import notify_landlord_document_reviewed_task
        from apps.common.cache import invalidate_property_cache, invalidate_documents_cache
        from django.db import transaction
        from django.utils import timezone

        count = 0
        for doc in queryset:
            old_status = doc.verification_status
            if old_status != LandlordDocument.VerificationStatus.REJECTED:
                doc.verification_status = LandlordDocument.VerificationStatus.REJECTED
                doc.reviewed_by = request.user
                doc.reviewed_at = timezone.now()
                doc.save(update_fields=["verification_status", "reviewed_by", "reviewed_at"])
                invalidate_documents_cache(landlord_id=doc.landlord_id, document_id=doc.pk)
                if doc.property_id:
                    invalidate_property_cache(property_id=doc.property_id)
                else:
                    invalidate_property_cache(landlord_id=doc.landlord_id)
                doc_id = str(doc.pk)
                transaction.on_commit(lambda d_id=doc_id, o_st=old_status: notify_landlord_document_reviewed_task.delay(d_id, previous_status=o_st))
                count += 1
        self.message_user(request, f"{count} document(s) rejected and landlord(s) notified.")

    def save_model(self, request, obj, form, change):
        from django.db import transaction
        from django.utils import timezone
        from apps.landloards.tasks import notify_landlord_document_reviewed_task
        from apps.common.cache import invalidate_property_cache, invalidate_documents_cache

        old_status = form.initial.get("verification_status") if change else None
        if change and "verification_status" in form.changed_data and not obj.reviewed_by:
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)
        if change and "verification_status" in form.changed_data:
            doc_id = str(obj.pk)
            transaction.on_commit(lambda: notify_landlord_document_reviewed_task.delay(doc_id, previous_status=old_status))
            invalidate_documents_cache(landlord_id=obj.landlord_id, document_id=obj.pk)
            if obj.property_id:
                invalidate_property_cache(property_id=obj.property_id)
            else:
                invalidate_property_cache(landlord_id=obj.landlord_id)


