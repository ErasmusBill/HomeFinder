from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from .selectors import (
    get_recent_properties,
    get_published_properties,
    get_property_by_slug,
    _apply_filters,
)
from apps.locations.models import Region, District, Town, Area
from apps.home_finder.models import Property, PropertyInterest
# Create your views here.

def home(request):
    """
    Home page view.

    The hero search box is a GET form that submits to the listing page
    (/properties/) with the filter values in the query string. The home
    page itself only needs a small context:
      - `properties`     : the "Featured Properties" grid (filtered if ?q=…)
      - `filters`        : current hero-search values (for pre-selecting)
      - `regions`        : for the Location dropdown
      - `popular_regions`: a small set of regions for the "Popular Searches"
                           tags so the tags can actually link somewhere.
      - room_type_choices, payment_period_choices, price_choices: model/UI data.
    """
    # The hero search only carries a subset of the full filter set; we still
    # reuse _apply_filters so "Featured Properties" reacts to ?q= too.
    hero_filters = {
        "q": request.GET.get("q", ""),
        "region": request.GET.get("region", ""),
        "room_type": request.GET.get("room_type", ""),
        "min_price": request.GET.get("min_price", ""),
        "max_price": request.GET.get("max_price", ""),
    }

    qs = Property.objects.filter(
        publication_status=Property.PublicationStatus.PUBLISHED,
        verification_status=Property.VerificationStatus.VERIFIED,
        is_available=True,
    ).select_related("region", "district", "town", "area").prefetch_related("amenities", "media")

    properties = list(_apply_filters(qs, hero_filters).order_by("-created_at")[:12])

    regions = Region.objects.all().order_by("name")
    # "Popular searches" on the home page map to the first few regions, so
    # clicking a tag actually filters properties on /properties/.
    popular_regions = list(regions[:5])

    return render(
        request,
        'home_finder/index.html',
        {
            "properties": properties,
            "filters": hero_filters,
            "regions": regions,
            "popular_regions": popular_regions,
            "room_type_choices": Property.RoomType.choices,
            "payment_period_choices": Property.PaymentPeriod.choices,
            "price_choices": [500, 1000, 2500, 5000, 10000, 20000],
        },
    )


def cascade_locations(request):
    """
    AJAX endpoint used by the filter dropdowns to fetch child options.

    Query params:
      - type: 'districts' | 'towns' | 'areas'
      - parent: pk of the parent (region for districts, district for towns, town for areas)

    Returns: JSON list of {"id": "...", "name": "..."}
    """
    kind = request.GET.get("type", "")
    parent = request.GET.get("parent", "")

    items = []
    if kind == "districts" and parent:
        items = list(
            District.objects.filter(region__pk=parent)
            .order_by("name")
            .values("id", "name")
        )
    elif kind == "towns" and parent:
        items = list(
            Town.objects.filter(district__pk=parent)
            .order_by("name")
            .values("id", "name")
        )
    elif kind == "areas" and parent:
        items = list(
            Area.objects.filter(town__pk=parent)
            .order_by("name")
            .values("id", "name")
        )

    # Serialize UUIDs as strings so JSON output is stable.
    for it in items:
        it["id"] = str(it["id"])
    return JsonResponse({"results": items})


def _get_filter_context(request):
    """
    Build the context needed to render the property_list page:
      - `page_obj` : the paginated, filtered properties
      - `properties` : same as page_obj (kept for template compatibility)
      - `filters` : dict of currently-selected filter values
      - `regions`, `districts`, `towns`, `areas` : for the dropdowns
      - `room_type_choices`, `payment_period_choices` : model choices
    """
    filters = {
        "q": request.GET.get("q", ""),
        "region": request.GET.get("region", ""),
        "district": request.GET.get("district", ""),
        "town": request.GET.get("town", ""),
        "area": request.GET.get("area", ""),
        "room_type": request.GET.get("room_type", ""),
        "payment_period": request.GET.get("payment_period", ""),
        "min_price": request.GET.get("min_price", ""),
        "max_price": request.GET.get("max_price", ""),
        "bedrooms": request.GET.get("bedrooms", ""),
        "furnished": request.GET.get("furnished", ""),
        "unfurnished": request.GET.get("unfurnished", ""),
    }

    # Build a base queryset so we can apply filters and paginate
    qs = Property.objects.filter(
        publication_status=Property.PublicationStatus.PUBLISHED,
        verification_status=Property.VerificationStatus.VERIFIED,
        is_available=True,
    ).select_related("region", "district", "town", "area").prefetch_related("amenities", "media")

    qs = _apply_filters(qs, filters)
    qs = qs.order_by("-created_at")

    paginator = Paginator(qs, 12)  # 12 per page is more user-friendly than 50
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Cascading dropdowns:
    #   - If a region is selected, only show its districts.
    #   - If a district is selected, only show its towns.
    #   - If a town is selected, only show its areas.
    regions = Region.objects.all().order_by("name")

    districts_qs = District.objects.select_related("region").order_by("name")
    if filters["region"]:
        districts_qs = districts_qs.filter(
            Q(pk=filters["region"]) | Q(region__pk=filters["region"]) | Q(region__slug=filters["region"])
        )
    districts = districts_qs

    towns_qs = Town.objects.select_related("district__region").order_by("name")
    if filters["district"]:
        towns_qs = towns_qs.filter(
            Q(pk=filters["district"]) | Q(district__pk=filters["district"]) | Q(district__slug=filters["district"])
        )
    elif filters["region"]:
        towns_qs = towns_qs.filter(district__region__pk=filters["region"])
    towns = towns_qs

    areas_qs = Area.objects.select_related("town__district__region").order_by("name")
    if filters["town"]:
        areas_qs = areas_qs.filter(
            Q(pk=filters["town"]) | Q(town__pk=filters["town"]) | Q(town__slug=filters["town"])
        )
    elif filters["district"]:
        areas_qs = areas_qs.filter(town__district__pk=filters["district"])
    elif filters["region"]:
        areas_qs = areas_qs.filter(town__district__region__pk=filters["region"])
    areas = areas_qs

    return {
        "page_obj": page_obj,
        "properties": page_obj,
        "filters": filters,
        "regions": regions,
        "districts": districts,
        "towns": towns,
        "areas": areas,
        "room_type_choices": Property.RoomType.choices,
        "payment_period_choices": Property.PaymentPeriod.choices,
        "bedroom_choices": [1, 2, 3, 4, 5],
    }


def get_all_properties(request):
    context = _get_filter_context(request)
    return render(request, 'home_finder/property_list.html', context)


def get_property_detail(request, slug):
    property_obj = get_property_by_slug(slug=slug)
    
    if property_obj:
        from django.db.models import F
        from apps.home_finder.models import Property
        
        viewed_cookie_name = f'viewed_property_{property_obj.id}'
        if not request.COOKIES.get(viewed_cookie_name):
            # Only increment if the cookie is not present
            Property.objects.filter(id=property_obj.id).update(views_count=F("views_count") + 1)
            # The view count won't be updated on the property_obj itself unless we refresh,
            # but that's fine since it will be accurate on the next load.
            
    has_expressed_interest = False
    if (
        property_obj
        and request.user.is_authenticated
        and request.user.role == request.user.Role.TENANT
    ):
        has_expressed_interest = PropertyInterest.objects.filter(
            property=property_obj,
            tenant=request.user,
        ).exists()

    response = render(request, 'home_finder/property_detail.html', {
        'property': property_obj,
        'has_expressed_interest': has_expressed_interest,
    })
    
    if property_obj and not request.COOKIES.get(viewed_cookie_name):
        response.set_cookie(viewed_cookie_name, 'true', max_age=86400) # 24 hours
        
    return response


@login_required
@require_POST
def express_property_interest(request, slug):
    """Let a tenant opt in to contact from the owner of a listing."""
    if request.user.role != request.user.Role.TENANT:
        messages.error(request, "Only tenant accounts can register interest in a property.")
        return redirect('home_finder:property_detail', slug=slug)

    property_obj = get_object_or_404(
        Property,
        slug=slug,
        publication_status=Property.PublicationStatus.PUBLISHED,
        verification_status=Property.VerificationStatus.VERIFIED,
        is_available=True,
    )
    _, created = PropertyInterest.objects.get_or_create(
        property=property_obj,
        tenant=request.user,
    )
    if created:
        messages.success(request, "Your interest has been shared with the property owner.")
    else:
        messages.info(request, "You have already registered your interest in this property.")
    return redirect('home_finder:property_detail', slug=slug)
