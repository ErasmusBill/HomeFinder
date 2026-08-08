from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import PermissionsMixin
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Sum, F
from django.shortcuts import get_object_or_404, redirect, render

from apps.account.models import User
from apps.home_finder.forms import (
    AmenityForm,
    PropertyCreateForm,
    PropertyMediaForm,
    PropertyUpdateForm,
    PropertyVerificationForm,
    LandlordDocumentForm,
)
from apps.home_finder.models import Amenity, Property, PropertyMedia, LandlordDocument
from apps.home_finder.tasks import process_property_cover, process_property_media
from apps.landloards.forms import PropertyMediaFormSet
from apps.locations.models import Region, District, Town, Area
from apps.Subscription.models import LandlordSubscription, SubscriptionPlan

CACHE_TTL = getattr(settings, 'CACHE_TTL', 300)


def amenity_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["home_finder", "amenities", prefix, *[str(arg) for arg in args if arg is not None]])


def property_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["home_finder", "properties", prefix, *[str(arg) for arg in args if arg is not None]])


def document_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["home_finder", "documents", prefix, *[str(arg) for arg in args if arg is not None]])


def _invalidate_amenity_cache():
    cache.delete(amenity_cache_key("all"))


def _invalidate_property_cache(user_id, property_id=None):
    cache.delete(property_cache_key(f"user_{user_id}"))
    cache.delete(property_cache_key("all"))
    if property_id:
        cache.delete(property_cache_key("detail", property_id))


def _invalidate_document_cache(landlord_id, document_id=None):
    cache.delete(document_cache_key(f"landlord_{landlord_id}"))
    cache.delete(document_cache_key("all"))
    if document_id:
        cache.delete(document_cache_key("detail", document_id))



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
def create_amenity(request):
    if request.user.role != request.user.Role.LANDLORD and request.user.role != request.user.Role.ADMIN and not request.user.is_staff or not request.user.is_superuser:
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
def update_amenity(request, amenity_id: str):
    if request.user.role != request.user.Role.LANDLORD and request.user.role != request.user.Role.ADMIN and not request.user.is_staff:
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
def delete_amenity(request, amenity_id: str):
    if request.user.role != request.user.Role.LANDLORD and request.user.role != request.user.Role.ADMIN and not request.user.is_staff:
        messages.error(request, "Access denied. Only landlords and administrators can delete amenities.")
        return redirect('landloards:landloards_dashboard')

    amenity = get_object_or_404(Amenity, id=amenity_id)
    amenity.delete()
    _invalidate_amenity_cache()
    messages.success(request, 'Amenity deleted successfully.')
    return redirect('landloards:amenity_list')




@login_required
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
def list_landlord_subscription(request):
    user = request.user

    if user.role not in (User.Role.ADMIN, User.Role.LANDLORD, "admin", "landlord"):
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    if _is_admin(user):
        subscriptions = (
            LandlordSubscription.objects
            .select_related('plan', 'landlord')
            .order_by('-created_at')
        )
        active_subscription = None
    else:
        subscriptions = (
            LandlordSubscription.objects
            .filter(landlord=user)
            .select_related('plan')
            .order_by('-created_at')
        )
        active_subscription = (
            subscriptions
            .filter(status=LandlordSubscription.Status.SUCCESS, is_active=True)
            .order_by('-end_date')
            .first()
        )

    return render(request, 'landloards/landlord_subscription_list.html', {
        'subscriptions': subscriptions,
        'active_subscription': active_subscription,
    })


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
        return redirect('subscription:list')

    is_upgrade = new_plan.price > active_subscription.plan.price

    return render(request, 'landloards/confirm_plan_change.html', {
        'current_subscription': active_subscription,
        'new_plan': new_plan,
        'is_upgrade': is_upgrade,
    })



@login_required
def landlords_dashboard(request):
    user = request.user

    if not user.is_authenticated or user.role not in ["admin", "landlord"]:
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    # Filter properties based on user role
    if user.role == "admin":
        properties_qs = Property.objects.all()
    else:
        properties_qs = Property.objects.filter(landlord=user)

    total_properties = properties_qs.count()
    total_views = properties_qs.aggregate(total_views=Sum('views_count'))['total_views'] or 0

    # Locations summary breakdown counts
    total_regions = Region.objects.count()
    total_districts = District.objects.count()
    total_towns = Town.objects.count()
    total_areas = Area.objects.count()

    # Recent locations added
    recent_locations = Area.objects.select_related('town__district__region').order_by('-created_at')[:3]

    total_amenities = Amenity.objects.count()
    popular_amenities = Amenity.objects.annotate(
        property_count=Count('properties')
    ).order_by('-property_count')[:5]

    most_added_amenity = popular_amenities[0] if popular_amenities else None

    context = {
        "total_properties": total_properties,
        "total_views": total_views,
        "total_regions": total_regions,
        "total_districts": total_districts,
        "total_towns": total_towns,
        "total_areas": total_areas,
        "recent_locations": recent_locations,
        "total_amenities": total_amenities,
        "most_added_amenity": most_added_amenity,
        "popular_amenities": popular_amenities,
    }

    return render(request, "landloards/dashboard.html", context)


def property_detail(request, slug):
    user = request.user

    if not user.is_authenticated or user.role not in ["admin", "landlord"]:
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    Property.objects.filter(slug=slug).update(views_count=F("views_count") + 1)

    property_obj = get_object_or_404(
        Property.objects.select_related(
            "landlord", "region", "district", "town", "area"
        ).prefetch_related("media", "amenities"),
        slug=slug
    )

    context = {
        "property": property_obj,
    }
    return render(request, "landloards/property_detail_admin.html", context)


@login_required
def list_properties_related_landlords(request):
    user = request.user

    if not user.is_authenticated or user.role not in ["admin", "landlord"]:
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
def list_properties(request):
    if request.user.role != request.user.Role.LANDLORD and request.user.role != request.user.Role.ADMIN and not request.user.is_staff:
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
def create_property(request):
    if request.user.role != request.user.Role.LANDLORD and request.user.role != request.user.Role.ADMIN and not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Only registered landlords and administrators can create properties.")
        return redirect('landloards:landloards_dashboard')

    if request.method == 'POST':
        form = PropertyCreateForm(request.POST, request.FILES)
        media_formset = PropertyMediaFormSet(request.POST, request.FILES)

        if form.is_valid() and media_formset.is_valid():
            property_obj = form.save(commit=False)

            if request.user.role == request.user.Role.LANDLORD:
                property_obj.landlord = request.user
            elif not property_obj.landlord_id:
                property_obj.landlord = request.user

            property_obj.save()
            form.save_m2m()

            # Save formset items linked to the newly created property
            media_formset.instance = property_obj
            saved_media_items = media_formset.save()

            # Dispatch celery tasks for newly added media files
            for media in saved_media_items:
                if not media.is_processed:
                    process_property_media.delay(str(media.id))

            if property_obj.cover_image:
                process_property_cover.delay(str(property_obj.id))

            _invalidate_property_cache(request.user.id)
            messages.success(request, 'Property created successfully.')
            return redirect('landloards:property_list')
        else:
            messages.error(request, 'Error creating property. Please check the fields below.')
    else:
        form = PropertyCreateForm()
        media_formset = PropertyMediaFormSet()

    return render(request, 'landloards/property_form.html', {
        'form': form,
        'media_formset': media_formset,
        'is_update': False
    })


@login_required
def update_property(request, property_id: str):
    if request.user.role != request.user.Role.LANDLORD and request.user.role != request.user.Role.ADMIN and not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('landloards:dashboard')

    if request.user.role == request.user.Role.ADMIN or request.user.is_staff:
        property_obj = get_object_or_404(Property, id=property_id)
    else:
        property_obj = get_object_or_404(Property, id=property_id, landlord=request.user)

    if request.method == 'POST':
        form = PropertyUpdateForm(request.POST, request.FILES, instance=property_obj)
        media_formset = PropertyMediaFormSet(request.POST, request.FILES, instance=property_obj)

        if form.is_valid() and media_formset.is_valid():
            updated_property = form.save()

            # Save media formset changes (handles additions, edits, and deletions)
            saved_media_items = media_formset.save()
            for media in saved_media_items:
                if not media.is_processed:
                    process_property_media.delay(str(media.id))

            if 'cover_image' in form.changed_data and updated_property.cover_image:
                process_property_cover.delay(str(updated_property.id))

            _invalidate_property_cache(property_obj.landlord_id, property_id)
            messages.success(request, 'Property updated successfully.')
            return redirect('landloards:property_list')
        else:
            messages.error(request, 'Error updating property. Please check the fields below.')
    else:
        form = PropertyUpdateForm(instance=property_obj)
        media_formset = PropertyMediaFormSet(instance=property_obj)

    return render(request, 'landloards/property_form.html', {
        'form': form,
        'media_formset': media_formset,
        'property': property_obj,
        'is_update': True
    })


@login_required
def delete_property(request, property_id: str):
    if request.user.role != request.user.Role.LANDLORD and request.user.role != request.user.Role.ADMIN and not request.user.is_staff:
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
    if not request.user.is_staff and request.user.role != request.user.Role.ADMIN:
        messages.error(request, "Unauthorized action. Only admins can verify properties.")
        return redirect('landloards:landloards_dashboard')

    property_obj = get_object_or_404(Property, id=property_id)
    if request.method == 'POST':
        form = PropertyVerificationForm(request.POST, instance=property_obj)
        if form.is_valid():
            form.save()
            _invalidate_property_cache(property_obj.landlord_id, property_id)
            messages.success(request, 'Property verification status updated.')
            return redirect('landloards:property_list')
        else:
            messages.error(request, 'Error updating verification status.')
    else:
        form = PropertyVerificationForm(instance=property_obj)
    return render(request, 'landloards/property_verification.html', {'form': form, 'property': property_obj})


@login_required
def add_property_media(request, property_id: str):
    if request.user.role != request.user.Role.LANDLORD and request.user.role != request.user.Role.ADMIN and not request.user.is_staff:
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
def delete_property_media(request, media_id: str):
    if request.user.role != request.user.Role.LANDLORD and request.user.role != request.user.Role.ADMIN and not request.user.is_staff:
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