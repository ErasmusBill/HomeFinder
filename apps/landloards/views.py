from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import PermissionsMixin
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Sum, F
from django.shortcuts import get_object_or_404, redirect, render

from apps.home_finder.forms import (
    AmenityForm,
    PropertyCreateForm,
    PropertyMediaForm,
    PropertyUpdateForm,
    PropertyVerificationForm,
)
from apps.home_finder.models import Amenity, Property, PropertyMedia
from apps.home_finder.tasks import process_property_cover, process_property_media
from apps.landloards.forms import PropertyMediaFormSet
from apps.locations.models import Region, District, Town, Area
from apps.Subscription.models import LandlordSubscription

CACHE_TTL = getattr(settings, 'CACHE_TTL', 300)


def amenity_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["home_finder", "amenities", prefix, *[str(arg) for arg in args if arg is not None]])


def property_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["home_finder", "properties", prefix, *[str(arg) for arg in args if arg is not None]])


def _invalidate_amenity_cache():
    cache.delete(amenity_cache_key("all"))


def _invalidate_property_cache(user_id, property_id=None):
    cache.delete(property_cache_key(f"user_{user_id}"))
    cache.delete(property_cache_key("all"))
    if property_id:
        cache.delete(property_cache_key("detail", property_id))


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
def list_landlord_subscription(request):
    global subscription
    user = request.user

    if not user.is_authenticated or user.role not in ["admin", "landlord"]:
        messages.error(request, "Access denied.")
        return redirect("home_finder:home")

    if user.role == "admin":
        subscription_qs = LandlordSubscription.objects.all()
    elif user.role == "landlord":
        subscription_qs = LandlordSubscription.objects.filter(lanlord=user)

    return render(request, 'landloards/landlord_subscription_list.html', {'subscription': subscription_qs})




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