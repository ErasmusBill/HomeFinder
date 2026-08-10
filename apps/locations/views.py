import json

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.cache import invalidate_locations_cache
from .forms import AreaForm, DistrictForm, RegionForm, TownForm
from .models import Area, District, Region, Town
from .selectors import get_all_locations

CACHE_TTL = getattr(settings, 'CACHE_TTL', 300)


def location_cache_key(prefix: str, *args, **kwargs):
    return ":".join(["properties", prefix, *[str(arg) for arg in args if arg is not None]])


def _invalidate_location_cache(location_obj=None):
    invalidate_locations_cache()


def _clear_location_sessions(request):
    for key in ['pending_region_id', 'pending_district_id', 'pending_town_id']:
        request.session.pop(key, None)


def create_region(request):
    if request.method == 'GET':
        _clear_location_sessions(request)

    if request.method == 'POST':
        form = RegionForm(request.POST)
        if form.is_valid():
            region = form.save()
            _invalidate_location_cache()
            messages.success(
                request,
                'Region created successfully! Now, add a district for this region.',
            )
            request.session['pending_region_id'] = str(region.id)
            return redirect('locations:add_district')
        else:
            messages.error(request, 'Error creating region')
    else:
        form = RegionForm()

    return render(
        request,
        'locations/create_region.html',
        {'form': form, 'is_update': False},
    )


def update_region(request, region_id: str):
    region = get_object_or_404(Region, id=region_id)
    if request.method == 'POST':
        form = RegionForm(request.POST, instance=region)
        if form.is_valid():
            form.save()
            _invalidate_location_cache()
            messages.success(request, 'Region updated successfully')
            return redirect('locations:list_locations')
        else:
            messages.error(request, 'Error updating region')
    else:
        form = RegionForm(instance=region)

    return render(
        request,
        'locations/create_region.html',
        {'form': form, 'is_update': True, 'object_name': region.name},
    )


def delete_region(request, region_id: str):
    region = get_object_or_404(Region, id=region_id)
    region.delete()
    _invalidate_location_cache()
    messages.success(request, 'Region deleted successfully')
    return redirect('locations:list_locations')


def add_district(request):
    # Retrieve the pending region ID saved during region creation
    pending_region_id = request.session.get('pending_region_id')
    initial_region = None

    if pending_region_id:
        initial_region = Region.objects.filter(id=pending_region_id).first()

    if request.method == "POST":
        form = DistrictForm(request.POST)
        if form.is_valid():
            district = form.save(commit=False)
            # If the form didn't explicitly pick a region, default to the session one
            if not district.region and initial_region:
                district.region = initial_region
            district.save()
            _invalidate_location_cache()

            # Save the new district ID in the session for the next step (Town)
            request.session['pending_district_id'] = str(district.id)
            return redirect('locations:add_town')
        else:
            # Pre-select the region in the form if available
            initial_data = {'region': initial_region} if initial_region else None
            form = DistrictForm(initial=initial_data)
    else:
        initial_data = {'region': initial_region} if initial_region else None
        form = DistrictForm(initial=initial_data)

    context = {
        'form': form,
        'region': initial_region,
        'is_update': False,
    }
    return render(request, 'locations/add_district.html', context)


def update_district(request, district_id: str):
    district = get_object_or_404(District, id=district_id)
    if request.method == 'POST':
        form = DistrictForm(request.POST, instance=district)
        if form.is_valid():
            form.save()
            _invalidate_location_cache()
            messages.success(request, 'District updated successfully')
            return redirect('locations:list_locations')
        else:
            messages.error(request, 'Error updating district')
            return redirect('locations:list_locations')
    else:
        form = DistrictForm(instance=district)
        return render(request, 'locations/add_district.html', {'form': form})


def add_town(request):
    district_id = request.session.get('pending_district_id')
    district = District.objects.filter(id=district_id).first() if district_id else None

    regions = Region.objects.all().order_by('name')
    districts = District.objects.select_related('region').order_by('name')
    district_region_map = json.dumps({str(d.id): str(d.region_id) for d in districts})

    if request.method == 'POST':
        form = TownForm(request.POST)
        if form.is_valid():
            town = form.save(commit=False)
            if district and not town.district_id:
                town.district = district
            town.save()
            _invalidate_location_cache()

            messages.success(
                request, 'Town added successfully! Now, add an area for this town.'
            )
            request.session['pending_town_id'] = str(town.id)

            if district_id:
                return redirect('locations:add_area')
            return redirect('locations:list_locations')
        else:
            messages.error(request, 'Error adding town')
    else:
        initial_data = {'district': district} if district else {}
        form = TownForm(initial=initial_data)

    return render(
        request,
        'locations/add_town.html',
        {
            'form': form,
            'district': district,
            'regions': regions,
            'district_region_map': district_region_map,
        },
    )


def update_town(request, town_id: str):
    town = get_object_or_404(Town, id=town_id)
    regions = Region.objects.all().order_by('name')
    districts = District.objects.select_related('region').order_by('name')
    district_region_map = json.dumps({str(d.id): str(d.region_id) for d in districts})

    if request.method == 'POST':
        form = TownForm(request.POST, instance=town)
        if form.is_valid():
            form.save()
            _invalidate_location_cache()
            messages.success(request, 'Town updated successfully')
            return redirect('locations:list_locations')
        else:
            messages.error(request, 'Error updating town')
            return redirect('locations:list_locations')
    else:
        form = TownForm(instance=town)

    return render(
        request,
        'locations/add_town.html',
        {
            'form': form,
            'is_update': True,
            'object_name': town.name,
            'regions': regions,
            'district_region_map': district_region_map,
        },
    )


def add_area(request):
    town_id = request.session.get('pending_town_id')
    town = Town.objects.filter(id=town_id).first() if town_id else None

    if request.method == 'POST':
        form = AreaForm(request.POST)
        if form.is_valid():
            area = form.save(commit=False)
            if town and not area.town_id:
                area.town = town
            area.save()
            _invalidate_location_cache()

            messages.success(
                request, 'Complete location hierarchy created successfully!'
            )

            for key in [
                'pending_region_id',
                'pending_district_id',
                'pending_town_id',
            ]:
                request.session.pop(key, None)

            return redirect('locations:list_locations')
        else:
            messages.error(request, 'Error adding area')
            return redirect('locations:list_locations')
    else:
        initial_data = {'town': town} if town else {}
        form = AreaForm(initial=initial_data)
        return render(request, 'locations/add_area.html', {'form': form, 'town': town})


def update_area(request, area_id: str):
    area = get_object_or_404(Area, id=area_id)
    if request.method == 'POST':
        form = AreaForm(request.POST, instance=area)
        if form.is_valid():
            form.save()
            _invalidate_location_cache()
            messages.success(request, 'Area updated successfully')
            return redirect('locations:list_locations')
        else:
            messages.error(request, 'Error updating area')
            return redirect('locations:list_locations')
    else:
        form = AreaForm(instance=area)
        return render(request, 'locations/add_area.html', {'form': form})


def list_locations(request):
    _clear_location_sessions(request)

    locations = get_all_locations()

    paginator = Paginator(locations, 50)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)

    return render(request, 'locations/location.html', {'locations': page_obj})