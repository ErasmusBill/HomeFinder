from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import PermissionsMixin
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Sum, F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.account.models import User
from apps.home_finder.forms import (
    AmenityForm,
    PropertyCreateForm,
    PropertyMediaForm,
    PropertyUpdateForm,
    PropertyVerificationForm,
    LandlordDocumentForm,
    LandlordDocumentReviewForm,
)
from apps.home_finder.models import Amenity, Property, PropertyMedia, LandlordDocument
from apps.home_finder.tasks import process_property_cover, process_property_media
from apps.landloards.forms import (
    PropertyMediaFormSet,
    PropertyDocumentFormSet,
    LandlordIdentityDocumentForm,
)
from apps.landloards.selectors import (
    get_landlord_viewing_request,
    get_landlord_viewing_request_counts,
    invalidate_landlord_viewing_requests_cache,
)
from apps.landloards.tasks import (
    notify_admins_property_created_task,
    notify_landlord_document_reviewed_task,
    notify_landlord_property_verified_task,
)
from apps.Subscription.models import LandlordSubscription, SubscriptionPlan
from apps.Subscription.guards import subscription_required
from apps.tenant.models import ViewingRequest
from apps.landloards.guards import onboarding_required

CACHE_TTL = getattr(settings, 'CACHE_TTL', 300)


def amenity_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["home_finder", "amenities", prefix, *[str(arg) for arg in args if arg is not None]])


def property_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["home_finder", "properties", prefix, *[str(arg) for arg in args if arg is not None]])


def document_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["home_finder", "documents", prefix, *[str(arg) for arg in args if arg is not None]])


from apps.common.cache import (
    invalidate_property_cache,
    invalidate_amenities_cache,
    invalidate_documents_cache,
)

def _invalidate_amenity_cache():
    invalidate_amenities_cache()


def _invalidate_property_cache(user_id, property_id=None):
    invalidate_property_cache(landlord_id=user_id, property_id=property_id)


def _invalidate_document_cache(landlord_id, document_id=None):
    invalidate_documents_cache(landlord_id=landlord_id, document_id=document_id)



def _is_landlord(user):
    return user.role in (User.Role.LANDLORD, "landlord")


def _is_admin(user):
    return user.role in (User.Role.ADMIN, "admin") or getattr(user, "is_staff", False)


def _is_landlord_or_admin(user):
    return _is_landlord(user) or _is_admin(user)


def list_amenities(request):
    cache_key = amenity_cache_key("all")
    amenities = cache.get(cache_key)
    if amenities is None:
        amenities = list(Amenity.objects.all())
        cache.set(cache_key, amenities, CACHE_TTL)

    paginator = Paginator(amenities, 20)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)
    return render(request, 'landloards/amenity_list.html', {'amenities': page_obj})


@login_required
@subscription_required
def create_amenity(request):
    if not _is_landlord_or_admin(request.user):
        messages.error(request, "Access denied. Only landlords and administrators can create amenities.")
        return redirect('landloards:landloards_dashboard')

    if request.method == 'POST':
        form = AmenityForm(request.POST)
        if form.is_valid():
            form.save()
            _invalidate_amenity_cache()
            messages.success(request, 'Amenity created successfully.')
            return redirect('landloards:amenity_list')
        else:
            messages.error(request, 'Error creating amenity.')
    else:
        form = AmenityForm()
    return render(request, 'landloards/amenity_form.html', {'form': form})


@login_required
@subscription_required
def update_amenity(request, amenity_id: str):
    if not _is_landlord_or_admin(request.user):
        messages.error(request, "Access denied. Only landlords and administrators can update amenities.")
        return redirect('landloards:landloards_dashboard')

    amenity = get_object_or_404(Amenity, id=amenity_id)
    if request.method == 'POST':
        form = AmenityForm(request.POST, instance=amenity)
        if form.is_valid():
            form.save()
            _invalidate_amenity_cache()
            messages.success(request, 'Amenity updated successfully.')
            return redirect('landloards:amenity_list')
        else:
            messages.error(request, 'Error updating amenity.')
    else:
        form = AmenityForm(instance=amenity)
    return render(request, 'landloards/amenity_form.html', {'form': form, 'amenity': amenity})


@login_required
@subscription_required
def delete_amenity(request, amenity_id: str):
    if not _is_landlord_or_admin(request.user):
        messages.error(request, "Access denied. Only landlords and administrators can delete amenities.")
        return redirect('landloards:landloards_dashboard')

    amenity = get_object_or_404(Amenity, id=amenity_id)
    amenity.delete()
    _invalidate_amenity_cache()
    messages.success(request, 'Amenity deleted successfully.')
    return redirect('landloards:amenity_list')




@login_required
@subscription_required
def list_landlord_documents(request):
    user = request.user

    if not _is_landlord_or_admin(user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    if _is_admin(user):
        cache_key = document_cache_key("all")
        documents = cache.get(cache_key)
        if documents is None:
            documents = list(
                LandlordDocument.objects
                .select_related('landlord', 'property', 'reviewed_by')
                .order_by('-created_at')
            )
            cache.set(cache_key, documents, CACHE_TTL)
    else:
        cache_key = document_cache_key(f"landlord_{user.id}")
        documents = cache.get(cache_key)
        if documents is None:
            documents = list(
                LandlordDocument.objects
                .filter(landlord=user)
                .select_related('property', 'reviewed_by')
                .order_by('-created_at')
            )
            cache.set(cache_key, documents, CACHE_TTL)

    paginator = Paginator(documents, 20)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)

    return render(request, 'landloards/landlord_document_list.html', {
        'documents': page_obj,
    })


@login_required
@subscription_required
def create_landlord_document(request):
    """
    Landlord-only. Admins review documents rather than uploading on a
    landlord's behalf here, so unlike most other views in this file this
    one deliberately does NOT allow admin/staff access.
    """
    user = request.user

    if not _is_landlord(user):
        messages.error(request, "Only landlords can upload documents.")
        return redirect('landloards:landloards_dashboard')

    if request.method == 'POST':
        form = LandlordDocumentForm(request.POST, request.FILES, landlord=user)
        if form.is_valid():
            document = form.save(commit=False)
            document.landlord = user
            
            # Auto-verify National ID, and auto-verify other docs if National ID is already verified
            if document.document_type == LandlordDocument.DocumentType.NATIONAL_ID:
                document.verification_status = LandlordDocument.VerificationStatus.VERIFIED
            else:
                has_verified_id = LandlordDocument.objects.filter(
                    landlord=user,
                    document_type=LandlordDocument.DocumentType.NATIONAL_ID,
                    verification_status=LandlordDocument.VerificationStatus.VERIFIED
                ).exists()
                if has_verified_id:
                    document.verification_status = LandlordDocument.VerificationStatus.VERIFIED

            document.save()
            _invalidate_document_cache(user.id)
            messages.success(request, 'Document uploaded and pending review.')
            return redirect('landloards:landlord_document_list')
        else:
            messages.error(request, 'Error uploading document. Please check the fields below.')
    else:
        form = LandlordDocumentForm(landlord=user)

    return render(request, 'landloards/landlord_document_form.html', {
        'form': form,
        'is_update': False,
    })


@login_required
@subscription_required
def update_landlord_document(request, document_id: str):
    user = request.user

    if not _is_landlord_or_admin(user):
        messages.error(request, "Access denied.")
        return redirect('landloards:landloards_dashboard')

    if _is_admin(user):
        document = get_object_or_404(LandlordDocument, id=document_id)
    else:
        document = get_object_or_404(LandlordDocument, id=document_id, landlord=user)

    if document.verification_status == LandlordDocument.VerificationStatus.VERIFIED and not _is_admin(user):
        messages.error(
            request,
            "This document has already been verified and can't be edited. "
            "Please upload a new document if something needs to change."
        )
        return redirect('landloards:landlord_document_list')

    if request.method == 'POST':
        form = LandlordDocumentForm(
            request.POST, request.FILES, instance=document, landlord=document.landlord
        )
        if form.is_valid():
            updated_document = form.save(commit=False)
            # Editing resets verification — a changed file/type needs
            # re-review, it can't stay marked verified against new content.
            # Auto-verify National ID, and auto-verify other docs if National ID is already verified
            if updated_document.document_type == LandlordDocument.DocumentType.NATIONAL_ID:
                updated_document.verification_status = LandlordDocument.VerificationStatus.VERIFIED
            else:
                has_verified_id = LandlordDocument.objects.filter(
                    landlord=updated_document.landlord,
                    document_type=LandlordDocument.DocumentType.NATIONAL_ID,
                    verification_status=LandlordDocument.VerificationStatus.VERIFIED
                ).exists()
                if has_verified_id:
                    updated_document.verification_status = LandlordDocument.VerificationStatus.VERIFIED
                else:
                    updated_document.verification_status = LandlordDocument.VerificationStatus.PENDING

            updated_document.rejection_reason = ""
            updated_document.reviewed_by = None
            updated_document.reviewed_at = None
            updated_document.save()

            _invalidate_document_cache(document.landlord_id, document_id)
            messages.success(request, 'Document updated and pending re-review.')
            return redirect('landloards:landlord_document_list')
        else:
            messages.error(request, 'Error updating document. Please check the fields below.')
    else:
        form = LandlordDocumentForm(instance=document, landlord=document.landlord)

    return render(request, 'landloards/landlord_document_form.html', {
        'form': form,
        'document': document,
        'is_update': True,
    })


@login_required
@subscription_required
def delete_landlord_document(request, document_id: str):
    user = request.user

    if not _is_landlord_or_admin(user):
        messages.error(request, "Access denied.")
        return redirect('landloards:landloards_dashboard')

    if _is_admin(user):
        document = get_object_or_404(LandlordDocument, id=document_id)
    else:
        document = get_object_or_404(LandlordDocument, id=document_id, landlord=user)

    landlord_id = document.landlord_id
    document.file.delete(save=False)  # remove the underlying file from storage too
    document.delete()

    _invalidate_document_cache(landlord_id, document_id)
    messages.success(request, 'Document deleted successfully.')
    return redirect('landloards:landlord_document_list')


@login_required
def review_landlord_document(request, document_id: str):
    """
    Admin-only view to approve or reject an uploaded LandlordDocument.
    Updates verification_status, stamps reviewed_by / reviewed_at, and
    fires off an email task to the landlord.
    """
    if not _is_admin(request.user):
        messages.error(request, "Unauthorized action. Only admins can review documents.")
        return redirect('landloards:landlord_document_list')

    document = get_object_or_404(
        LandlordDocument.objects.select_related("landlord", "property"),
        id=document_id,
    )

    previous_status = document.verification_status

    if request.method == 'POST':
        form = LandlordDocumentReviewForm(request.POST, instance=document)
        if form.is_valid():
            reviewed = form.save(commit=False)
            # Only stamp the reviewer when the status actually moves out of
            # pending — leaves a "pending" doc with no reviewer attribution.
            if reviewed.verification_status != LandlordDocument.VerificationStatus.PENDING:
                reviewed.reviewed_by = request.user
                reviewed.reviewed_at = timezone.now()
                # If admin approved without writing a reason, clear any stale one.
                if reviewed.verification_status == LandlordDocument.VerificationStatus.VERIFIED:
                    reviewed.rejection_reason = ""
            reviewed.save()

            _invalidate_document_cache(document.landlord_id, document_id)
            if document.property_id:
                _invalidate_property_cache(document.landlord_id, document.property_id)
            else:
                _invalidate_property_cache(document.landlord_id)

            # Notify the landlord only if the status actually changed.
            if reviewed.verification_status != previous_status:
                notify_landlord_document_reviewed_task.delay(
                    str(reviewed.id), previous_status=previous_status,
                )

            messages.success(request, 'Document review updated and landlord notified.')
            return redirect('landloards:landlord_document_list')
        else:
            messages.error(request, 'Error updating document review.')
    else:
        form = LandlordDocumentReviewForm(instance=document)

    return render(request, 'landloards/landlord_document_review.html', {
        'form': form,
        'document': document,
    })


@login_required
def list_landlord_subscription(request):
    """Landlord billing history, active subscription, and plan selection view."""
    if request.user.role != User.Role.LANDLORD:
        messages.error(request, "Access restricted to landlords.")
        return redirect('dashboard')

    # Fetch the most recent active successful subscription
    active_subscription = LandlordSubscription.objects.filter(
        landlord=request.user,
        status=LandlordSubscription.Status.SUCCESS,
        is_active=True
    ).order_by('-end_date').first()

    # Fetch full billing / subscription logs for the history table
    subscriptions = LandlordSubscription.objects.filter(
        landlord=request.user
    ).select_related('plan').order_by('-created_at')

    # Fetch all subscription plans from the database (.all() or .filter(is_active=True))
    all_plans = SubscriptionPlan.objects.all()

    # Calculate active property listings count for the progress bar
    active_listings_count = 0
    if hasattr(request.user, 'properties'):
        active_listings_count = request.user.properties.filter(is_available=True).count()
    elif hasattr(request.user, 'property_set'):
        active_listings_count = request.user.property_set.filter(is_available=True).count()

    context = {
        'active_subscription': active_subscription,
        'subscriptions': subscriptions,
        # Providing multiple aliases guarantees compatibility with any template loop variable name
        'available_plans': all_plans,
        'plans': all_plans,
        'subscription_plans': all_plans,
        'active_listings_count': active_listings_count,
    }

    return render(request, 'landloards/landlord_subscription_list.html', context)

@login_required
def confirm_plan_change_view(request, plan_id):
    """
    Shown when a landlord with an active subscription picks a different
    plan. Tells them what will actually happen (immediate upgrade vs
    scheduled downgrade) and lets them back out and keep what they have,
    instead of silently kicking off a new payment.
    """
    new_plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)

    active_subscription = get_object_or_404(
        LandlordSubscription,
        landlord=request.user,
        status=LandlordSubscription.Status.SUCCESS,
        is_active=True,
    )

    if active_subscription.plan_id == new_plan.id:
        messages.info(request, f"You already have an active {new_plan.name} subscription.")
        return redirect('landloards:list_landlord_subscription')

    is_upgrade = new_plan.price > active_subscription.plan.price

    return render(request, 'landloards/confirm_plan_change.html', {
        'current_subscription': active_subscription,
        'new_plan': new_plan,
        'is_upgrade': is_upgrade,
    })



@login_required
@onboarding_required
@subscription_required
def landlords_dashboard(request):
    user = request.user

    if not _is_landlord_or_admin(user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    # Filter properties based on user role
    if user.role == "admin":
        properties_qs = Property.objects.all()
    else:
        properties_qs = Property.objects.filter(landlord=user)

    total_properties = properties_qs.count()
    total_views = properties_qs.aggregate(total_views=Sum('views_count'))['total_views'] or 0

    total_amenities = Amenity.objects.count()
    popular_amenities = Amenity.objects.annotate(
        property_count=Count('properties')
    ).order_by('-property_count')[:5]

    most_added_amenity = popular_amenities[0] if popular_amenities else None

    # Upcoming viewing requests (pending + confirmed) sorted by date
    # ascending so the dashboard always shows the *next* appointments
    # at the top. Limited to 5 so the widget stays scannable.
    from apps.tenant.models import ViewingRequest
    upcoming_viewings = list(
        ViewingRequest.objects
        .filter(
            property__landlord=user,
            status__in=[
                ViewingRequest.Status.PENDING,
                ViewingRequest.Status.CONFIRMED,
            ],
            preferred_date__gte=timezone.localdate(),
        )
        .select_related("tenant", "property", "property__area", "property__town")
        .order_by("preferred_date", "preferred_time")[:5]
    )
    # Landlord identity verification status
    identity_doc = LandlordDocument.objects.filter(
        landlord=user,
        document_type=LandlordDocument.DocumentType.NATIONAL_ID,
    ).order_by('-created_at').first()

    has_identity_doc = identity_doc is not None
    identity_verified = identity_doc is not None and identity_doc.verification_status == LandlordDocument.VerificationStatus.VERIFIED
    identity_status = identity_doc.verification_status if identity_doc else "missing"
    viewing_request_counts = get_landlord_viewing_request_counts(user)

    context = {
        "total_properties": total_properties,
        "total_views": total_views,
        "total_amenities": total_amenities,
        "most_added_amenity": most_added_amenity,
        "popular_amenities": popular_amenities,
        "upcoming_viewings": upcoming_viewings,
        "identity_doc": identity_doc,
        "has_identity_doc": has_identity_doc,
        "identity_verified": identity_verified,
        "identity_status": identity_status,
        **viewing_request_counts,
    }

    return render(request, "landloards/dashboard.html", context)


@login_required
@subscription_required
def property_detail(request, slug):
    user = request.user

    if not _is_landlord_or_admin(user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    if _is_admin(user):
        property_obj = get_object_or_404(
            Property.objects.select_related(
                "landlord", "region", "district", "town", "area"
            ).prefetch_related("media", "amenities"),
            slug=slug
        )
    else:
        property_obj = get_object_or_404(
            Property.objects.select_related(
                "landlord", "region", "district", "town", "area"
            ).prefetch_related("media", "amenities"),
            slug=slug,
            landlord=user
        )

    context = {
        "property": property_obj,
    }
    return render(request, "landloards/property_detail_admin.html", context)


@login_required
@subscription_required
def list_properties_related_landlords(request):
    user = request.user

    if not _is_landlord_or_admin(user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    cache_key = property_cache_key(f"user_{user.id}")
    properties = cache.get(cache_key)

    if properties is None:
        if user.role == "admin" or user.is_staff:
            queryset = Property.objects.all()
        else:
            queryset = Property.objects.filter(landlord=user)

        properties = list(
            queryset.select_related(
                "region", "district", "town", "area", "landlord"
            ).prefetch_related("amenities", "media").order_by("-created_at")
        )

        cache.set(cache_key, properties, CACHE_TTL)

    paginator = Paginator(properties, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "amenities": page_obj,
        "properties": page_obj,
    }

    return render(request, "landloards/properties_list.html", context)



@login_required
@subscription_required
def list_properties(request):
    if not _is_landlord_or_admin(request.user):
        messages.error(request, "Access denied. Only landlords and administrators can view this page.")
        return redirect('landloards:landloards_dashboard')

    user_id = request.user.id
    cache_key = property_cache_key(f"user_{user_id}")

    properties = cache.get(cache_key)
    if properties is None:
        if request.user.role == request.user.Role.ADMIN or request.user.is_staff:
            queryset = Property.objects.all()
        else:
            queryset = Property.objects.filter(landlord=request.user)

        properties = list(
            queryset.select_related('region', 'district', 'town', 'area', 'landlord')
            .prefetch_related('amenities', 'media')
        )
        cache.set(cache_key, properties, CACHE_TTL)

    paginator = Paginator(properties, 20)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)
    return render(request, 'landloards/property_list.html', {'properties': page_obj})


@login_required
@subscription_required
def create_property(request):
    if not _is_landlord_or_admin(request.user):
        messages.error(request, "Only registered landlords and administrators can create properties.")
        return redirect('landloards:landloards_dashboard')

    # Fetch all landlord documents from the database
    all_landlord_docs = LandlordDocument.objects.filter(
        landlord=request.user,
    ).select_related('property').order_by('-created_at')

    identity_doc = all_landlord_docs.filter(
        document_type=LandlordDocument.DocumentType.NATIONAL_ID,
    ).first()

    has_identity_doc = identity_doc is not None
    identity_verified = (
        identity_doc is not None
        and identity_doc.verification_status == LandlordDocument.VerificationStatus.VERIFIED
    )

    # Formset-level "must upload at least one doc" applies only when the
    # landlord has no Ghana Card on file at all. A Ghana Card in any
    # verification state (pending, rejected, verified) is sufficient to
    # create a listing without new uploads.
    docs_required = not has_identity_doc

    if request.method == 'POST':
        form = PropertyCreateForm(request.POST, request.FILES)
        media_formset = PropertyMediaFormSet(request.POST, request.FILES, prefix='media')
        doc_formset = PropertyDocumentFormSet(
            request.POST, request.FILES, prefix='docs', is_required=docs_required,
        )

        forms_valid = form.is_valid() and media_formset.is_valid() and doc_formset.is_valid()

        # Separate national_id rows from property-specific document rows
        national_id_rows = []
        property_doc_rows = []
        if doc_formset.is_valid():
            for dform in doc_formset.forms:
                if not dform.cleaned_data or dform.cleaned_data.get('DELETE'):
                    continue
                if not (dform.cleaned_data.get('file') or (dform.instance and dform.instance.pk and dform.instance.file)):
                    continue
                if dform.cleaned_data.get('document_type') == LandlordDocument.DocumentType.NATIONAL_ID:
                    national_id_rows.append(dform)
                else:
                    property_doc_rows.append(dform)

        # Ghana Card just uploaded in this submission counts as identity doc
        ghana_card_in_formset = bool(national_id_rows)

        # Enforce: when no Ghana Card on file at all, landlord must upload
        # either a Ghana Card or at least one property-specific document.
        # Any extra property-specific docs the landlord attaches — even if
        # still pending admin review — will not block the listing.
        if not has_identity_doc and not ghana_card_in_formset and len(property_doc_rows) == 0:
            # Attach error to formset
            doc_formset._non_form_errors = doc_formset.error_class(
                ["Please select Ghana Card / National ID or provide at least one property document (e.g. Proof of Ownership, Site Plan)."]
            )
            forms_valid = False

        if forms_valid:
            with transaction.atomic():
                property_obj = form.save(commit=False)

                if request.user.role == request.user.Role.LANDLORD:
                    property_obj.landlord = request.user
                elif not property_obj.landlord_id:
                    property_obj.landlord = request.user

                property_obj.save()
                form.save_m2m()

                # Save media formset items linked to the newly created property
                media_formset.instance = property_obj
                saved_media_items = media_formset.save()

                # Save ALL docs via formset (commit=False first so we can intercept)
                doc_formset.instance = property_obj
                saved_doc_items = doc_formset.save(commit=False)

                new_national_id_verified = False
                for doc in saved_doc_items:
                    doc.landlord = request.user
                    if doc.document_type == LandlordDocument.DocumentType.NATIONAL_ID:
                        # Save as a landlord-level identity doc (not property-specific)
                        doc.property = None
                        doc.verification_status = LandlordDocument.VerificationStatus.VERIFIED
                        new_national_id_verified = True
                    else:
                        doc.property = property_obj
                        if identity_verified or new_national_id_verified:
                            doc.verification_status = LandlordDocument.VerificationStatus.VERIFIED
                        else:
                            doc.verification_status = LandlordDocument.VerificationStatus.PENDING
                    doc.save()

                for doc in doc_formset.deleted_objects:
                    doc.delete()

                # Dispatch celery tasks asynchronously once transaction is durably committed
                media_ids_to_process = [str(media.id) for media in saved_media_items if not media.is_processed]
                created_prop_id = str(property_obj.id)

                def _dispatch_create_tasks():
                    for media_id in media_ids_to_process:
                        process_property_media.delay(media_id)
                    notify_admins_property_created_task.delay(created_prop_id)

                transaction.on_commit(_dispatch_create_tasks)

            _invalidate_property_cache(request.user.id)
            _invalidate_document_cache(request.user.id)
            messages.success(request, 'Property created successfully.')
            return redirect('landloards:property_list')
        else:

            messages.error(request, 'Error creating property. Please check the fields below.')
    else:
        form = PropertyCreateForm()
        media_formset = PropertyMediaFormSet(prefix='media')
        doc_formset = PropertyDocumentFormSet(prefix='docs', is_required=docs_required)

    return render(request, 'landloards/property_form.html', {
        'form': form,
        'media_formset': media_formset,
        'doc_formset': doc_formset,
        'identity_doc': identity_doc,
        'identity_verified': identity_verified,
        'docs_required': docs_required,
        'existing_documents': all_landlord_docs,
        'is_update': False
    })


@login_required
@subscription_required
def update_property(request, property_id: str):
    if not _is_landlord_or_admin(request.user):
        messages.error(request, "Access denied.")
        return redirect('landloards:landloards_dashboard')

    if request.user.role == request.user.Role.ADMIN or request.user.is_staff:
        property_obj = get_object_or_404(Property, id=property_id)
    else:
        property_obj = get_object_or_404(Property, id=property_id, landlord=request.user)

    all_landlord_docs = LandlordDocument.objects.filter(
        landlord=property_obj.landlord,
    ).select_related('property').order_by('-created_at')

    identity_doc = all_landlord_docs.filter(
        document_type=LandlordDocument.DocumentType.NATIONAL_ID,
    ).first()

    has_identity_doc = identity_doc is not None
    identity_verified = (
        identity_doc is not None
        and identity_doc.verification_status == LandlordDocument.VerificationStatus.VERIFIED
    )

    # Formset-level "must upload at least one doc" applies only when the
    # landlord has no Ghana Card on file at all. A Ghana Card in any
    # verification state (pending, rejected, verified) is sufficient to
    # create / update a listing without new uploads.
    docs_required = not has_identity_doc

    if request.method == 'POST':
        form = PropertyUpdateForm(request.POST, request.FILES, instance=property_obj)
        media_formset = PropertyMediaFormSet(request.POST, request.FILES, instance=property_obj, prefix='media')
        doc_formset = PropertyDocumentFormSet(
            request.POST, request.FILES, instance=property_obj,
            prefix='docs', is_required=docs_required,
        )

        forms_valid = form.is_valid() and media_formset.is_valid() and doc_formset.is_valid()

        if not has_identity_doc:
            valid_doc_count = sum(
                1 for dform in doc_formset.forms
                if dform.cleaned_data and not dform.cleaned_data.get('DELETE') and (dform.cleaned_data.get('file') or (dform.instance and dform.instance.pk and dform.instance.file))
            )
            if valid_doc_count == 0:
                doc_formset.non_form_errors().append(
                    "You must have your Ghana Card on file or provide at least one property document for this listing."
                )
                forms_valid = False

        if forms_valid:
            with transaction.atomic():
                updated_property = form.save()

                # Save media formset changes (handles additions, edits, and deletions)
                saved_media_items = media_formset.save()

                # Save property documents attached to this listing
                # Skip any brand-new doc that has no file — this is defensive
                # against legacy data and any edge case where the form's clean()
                # could not flag a row for deletion.
                saved_doc_items = [
                    d for d in doc_formset.save(commit=False)
                    if d.pk or (d.file and d.file.name)
                ]
                for doc in saved_doc_items:
                    doc.landlord = property_obj.landlord
                    
                    if doc.document_type == LandlordDocument.DocumentType.NATIONAL_ID:
                        doc.property = None
                        doc.verification_status = LandlordDocument.VerificationStatus.VERIFIED
                    else:
                        doc.property = updated_property
                        if identity_verified or doc.document_type == LandlordDocument.DocumentType.NATIONAL_ID:
                            doc.verification_status = LandlordDocument.VerificationStatus.VERIFIED
                        else:
                            # It's an update or new, if identity is not verified, it stays pending unless already verified
                            if doc.verification_status != LandlordDocument.VerificationStatus.VERIFIED:
                                doc.verification_status = LandlordDocument.VerificationStatus.PENDING

                    doc.save()
                for doc in doc_formset.deleted_objects:
                    doc.delete()

                media_ids_to_process = [str(media.id) for media in saved_media_items if not media.is_processed]
                updated_prop_id = str(updated_property.id)
                cover_changed = 'cover_image' in form.changed_data and bool(updated_property.cover_image)

                def _dispatch_update_tasks():
                    for media_id in media_ids_to_process:
                        process_property_media.delay(media_id)
                    if cover_changed:
                        process_property_cover.delay(updated_prop_id)

                transaction.on_commit(_dispatch_update_tasks)

            _invalidate_property_cache(property_obj.landlord_id, property_id)
            _invalidate_document_cache(property_obj.landlord_id)
            messages.success(request, 'Property updated successfully.')
            return redirect('landloards:property_list')

        else:
            messages.error(request, 'Error updating property. Please check the fields below.')
    else:
        form = PropertyUpdateForm(instance=property_obj)
        media_formset = PropertyMediaFormSet(instance=property_obj, prefix='media')
        doc_formset = PropertyDocumentFormSet(
            instance=property_obj, prefix='docs', is_required=docs_required,
        )

    return render(request, 'landloards/property_form.html', {
        'form': form,
        'media_formset': media_formset,
        'doc_formset': doc_formset,
        'identity_doc': identity_doc,
        'identity_verified': identity_verified,
        'docs_required': docs_required,
        'existing_documents': all_landlord_docs,
        'property': property_obj,
        'is_update': True
    })


@login_required
@subscription_required
def delete_property(request, property_id: str):
    if not _is_landlord_or_admin(request.user):
        messages.error(request, "Access denied.")
        return redirect('landloards:landloards_dashboard')

    if request.user.role == request.user.Role.ADMIN or request.user.is_staff:
        property_obj = get_object_or_404(Property, id=property_id)
    else:
        property_obj = get_object_or_404(Property, id=property_id, landlord=request.user)

    landlord_id = property_obj.landlord_id
    property_obj.delete()
    _invalidate_property_cache(landlord_id, property_id)
    messages.success(request, 'Property deleted successfully.')
    return redirect('landloards:property_list')


@login_required
def verify_property(request, property_id: str):
    if not _is_admin(request.user):
        messages.error(request, "Unauthorized action. Only admins can verify properties.")
        return redirect('landloards:landloards_dashboard')

    property_obj = get_object_or_404(Property, id=property_id)
    # Capture the pre-save status so the email task only fires on a real change.
    previous_status = property_obj.verification_status
    if request.method == 'POST':
        form = PropertyVerificationForm(request.POST, instance=property_obj)
        if form.is_valid():
            form.save()
            _invalidate_property_cache(property_obj.landlord_id, property_id)

            # Notify the landlord only if the status actually changed.
            if property_obj.verification_status != previous_status:
                notify_landlord_property_verified_task.delay(
                    str(property_obj.id), previous_status=previous_status,
                )

            messages.success(request, 'Property verification status updated.')
            return redirect('landloards:property_list')
        else:
            messages.error(request, 'Error updating verification status.')
    else:
        form = PropertyVerificationForm(instance=property_obj)
    return render(request, 'landloards/property_verification.html', {'form': form, 'property': property_obj})


@login_required
@subscription_required
def add_property_media(request, property_id: str):
    if not _is_landlord_or_admin(request.user):
        messages.error(request, "Access denied.")
        return redirect('landloards:landloards_dashboard')

    if request.user.role == request.user.Role.ADMIN or request.user.is_staff:
        property_obj = get_object_or_404(Property, id=property_id)
    else:
        property_obj = get_object_or_404(Property, id=property_id, landlord=request.user)

    if request.method == 'POST':
        form = PropertyMediaForm(request.POST, request.FILES)
        if form.is_valid():
            media = form.save(commit=False)
            media.property = property_obj
            media.save()

            process_property_media.delay(str(media.id))

            _invalidate_property_cache(property_obj.landlord_id, property_id)
            messages.success(request, 'Media added successfully.')
            return redirect('landloards:property_list')
        else:
            messages.error(request, 'Error adding media.')
    else:
        form = PropertyMediaForm()
    return render(request, 'home_finder/property_media_form.html', {'form': form, 'property': property_obj})


@login_required
@subscription_required
def delete_property_media(request, media_id: str):
    if not _is_landlord_or_admin(request.user):
        messages.error(request, "Access denied.")
        return redirect('landloards:landloards_dashboard')

    if request.user.role == request.user.Role.ADMIN or request.user.is_staff:
        media = get_object_or_404(PropertyMedia, id=media_id)
    else:
        media = get_object_or_404(PropertyMedia, id=media_id, property__landlord=request.user)

    property_id = str(media.property.id)
    landlord_id = media.property.landlord_id
    media.delete()
    _invalidate_property_cache(landlord_id, property_id)
    messages.success(request, 'Media deleted successfully.')
    return redirect('landloards:property_list')


# ---------------------------------------------------------------------------
# Viewing requests (landlord inbox)
# ---------------------------------------------------------------------------
# These views let a landlord see every viewing request for properties
# they own, and act on each one: confirm, decline (cancel), or propose
# a new date/time. Every state change invalidates the cached selectors
# and (via the tasks module) notifies the tenant by email + in-app
# notification.

def _is_landlord_viewing_requestor(user):
    """Landlords and admins can both browse the inbox."""
    return user.is_authenticated and (
        user.role == user.Role.LANDLORD or user.is_superuser
    )


@login_required
@subscription_required
def viewing_requests_list_view(request):
    """
    Landlord inbox of every viewing request for properties they own.

    Supports a ``status`` query-string filter (``pending`` / ``confirmed``
    / ``completed`` / ``cancelled``) so the landlord can focus on what
    still needs attention. Defaults to "pending" since that's the
    actionable subset.
    """
    if not _is_landlord_viewing_requestor(request.user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    status_filter = request.GET.get("status", "pending")
    valid_statuses = {s.value for s in ViewingRequest.Status}
    if status_filter != "all" and status_filter not in valid_statuses:
        status_filter = ViewingRequest.Status.PENDING

    requests_qs = ViewingRequest.objects.filter(
        property__landlord=request.user
    ).select_related(
        "tenant", "property", "property__region", "property__district", "property__area",
    )

    if status_filter != "all":
        requests_qs = requests_qs.filter(status=status_filter)

    viewing_requests = list(
        requests_qs.order_by("-preferred_date", "-preferred_time", "-created_at")
    )

    counts = get_landlord_viewing_request_counts(request.user)

    context = {
        "viewing_requests": viewing_requests,
        "current_status": status_filter,
        "status_choices": sorted(valid_statuses),
        **counts,
    }
    return render(request, "landloards/viewing_requests.html", context)


@login_required
@subscription_required
def viewing_request_detail_view(request, request_id):
    """Single-request detail (also used as a deep-link from emails)."""
    if not _is_landlord_viewing_requestor(request.user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    viewing_request = get_landlord_viewing_request(request.user, request_id)
    if viewing_request is None:
        messages.error(request, "Viewing request not found.")
        return redirect("landloards:viewing_requests")

    context = {"viewing_request": viewing_request}
    return render(request, "landloards/viewing_request_detail.html", context)


@login_required
@require_POST
@subscription_required
def confirm_viewing_request_view(request, request_id):
    """
    Landlord confirms a pending request. Status flips to ``confirmed``
    and the tenant gets an in-app notification + email.
    """
    if not _is_landlord_viewing_requestor(request.user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    viewing_request = get_landlord_viewing_request(request.user, request_id)
    if viewing_request is None:
        messages.error(request, "Viewing request not found.")
        return redirect("landloards:viewing_requests")

    previous_status = viewing_request.status
    if previous_status == ViewingRequest.Status.PENDING:
        viewing_request.status = ViewingRequest.Status.CONFIRMED
        viewing_request.save(update_fields=["status"])
        invalidate_landlord_viewing_requests_cache(request.user.pk)
        cache.delete(f"tenant:sidebar_counts:{viewing_request.tenant_id}")

        from .tasks import notify_landlord_viewing_request_status_task
        notify_landlord_viewing_request_status_task.delay(
            str(viewing_request.pk), "confirmed", previous_status,
        )
        messages.success(request, "Viewing request confirmed. The tenant has been notified.")
    else:
        messages.info(
            request,
            f"This viewing request is already {viewing_request.get_status_display().lower()}.",
        )

    return redirect("landloards:viewing_requests")


@login_required
@require_POST
@subscription_required
def decline_viewing_request_view(request, request_id):
    """
    Landlord declines a request. The status moves to ``cancelled`` (we
    reuse the cancelled status rather than introducing a new
    'declined' value — the semantics are identical from the tenant's
    perspective: their request no longer has a future appointment).
    """
    if not _is_landlord_viewing_requestor(request.user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    viewing_request = get_landlord_viewing_request(request.user, request_id)
    if viewing_request is None:
        messages.error(request, "Viewing request not found.")
        return redirect("landloards:viewing_requests")

    previous_status = viewing_request.status
    if previous_status in (
        ViewingRequest.Status.PENDING, ViewingRequest.Status.CONFIRMED,
    ):
        viewing_request.status = ViewingRequest.Status.CANCELLED
        viewing_request.save(update_fields=["status"])
        invalidate_landlord_viewing_requests_cache(request.user.pk)
        cache.delete(f"tenant:sidebar_counts:{viewing_request.tenant_id}")

        from .tasks import notify_landlord_viewing_request_status_task
        notify_landlord_viewing_request_status_task.delay(
            str(viewing_request.pk), "cancelled", previous_status,
        )
        messages.success(request, "Viewing request declined. The tenant has been notified.")
    else:
        messages.info(
            request,
            "This viewing request can no longer be declined.",
        )

    return redirect("landloards:viewing_requests")


@login_required
@subscription_required
def reschedule_viewing_request_view(request, request_id):
    """
    Landlord proposes a new date/time for a pending or confirmed
    request. The status resets to ``pending`` so the tenant has to
    re-acknowledge. Only the date + time are editable from this view —
    to change the property the landlord should ask the tenant to
    cancel + re-create.
    """
    from .forms import LandlordRescheduleViewingRequestForm

    if not _is_landlord_viewing_requestor(request.user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    viewing_request = get_landlord_viewing_request(request.user, request_id)
    if viewing_request is None:
        messages.error(request, "Viewing request not found.")
        return redirect("landloards:viewing_requests")

    if viewing_request.status not in (
        ViewingRequest.Status.PENDING, ViewingRequest.Status.CONFIRMED,
    ):
        messages.info(
            request,
            "Completed or cancelled requests can't be rescheduled.",
        )
        return redirect("landloards:viewing_requests")

    if request.method == "POST":
        form = LandlordRescheduleViewingRequestForm(request.POST, instance=viewing_request)
        if form.is_valid():
            previous_date = viewing_request.preferred_date
            previous_time = viewing_request.preferred_time
            updated = form.save(commit=False)
            # Reset to pending so the tenant sees the new proposal and
            # has a chance to confirm it explicitly.
            updated.status = ViewingRequest.Status.PENDING
            updated.save()
            invalidate_landlord_viewing_requests_cache(request.user.pk)
            cache.delete(f"tenant:sidebar_counts:{viewing_request.tenant_id}")

            from .tasks import notify_landlord_viewing_request_rescheduled_task
            notify_landlord_viewing_request_rescheduled_task.delay(
                str(updated.pk),
                previous_date.isoformat() if previous_date else "",
                previous_time.isoformat() if previous_time else "",
                proposed_by_landlord=True,
            )
            messages.success(
                request,
                "New time proposed. The tenant has been notified to confirm.",
            )
            return redirect("landloards:viewing_requests")
    else:
        form = LandlordRescheduleViewingRequestForm(instance=viewing_request)

    context = {"form": form, "viewing_request": viewing_request}
    return render(request, "landloards/viewing_request_reschedule.html", context)


@login_required
@require_POST
@subscription_required
def mark_viewing_completed_view(request, request_id):
    """Mark a confirmed viewing as completed (after the appointment)."""
    if not _is_landlord_viewing_requestor(request.user):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    viewing_request = get_landlord_viewing_request(request.user, request_id)
    if viewing_request is None:
        messages.error(request, "Viewing request not found.")
        return redirect("landloards:viewing_requests")

    if viewing_request.status == ViewingRequest.Status.CONFIRMED:
        viewing_request.status = ViewingRequest.Status.COMPLETED
        viewing_request.save(update_fields=["status"])
        invalidate_landlord_viewing_requests_cache(request.user.pk)
        cache.delete(f"tenant:sidebar_counts:{viewing_request.tenant_id}")

        from .tasks import notify_landlord_viewing_request_status_task
        notify_landlord_viewing_request_status_task.delay(
            str(viewing_request.pk), "completed", ViewingRequest.Status.CONFIRMED,
        )
        messages.success(request, "Marked as completed.")
    else:
        messages.info(request, "Only confirmed viewings can be marked as completed.")

    return redirect("landloards:viewing_requests")
