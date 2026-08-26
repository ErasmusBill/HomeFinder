import random
import time
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404
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
from apps.home_finder.models import Property, PropertyInterest, LandlordDocument
# Create your views here.


def get_shuffled_featured_properties(limit: int = 4):
    """
    Returns exactly `limit` (default 4) verified, available, and published
    properties. The selection is randomized deterministically per 1-minute
    (60-second) window and cached in Redis/memory so every request within
    the same 1-minute epoch receives the same 4 properties before rotating.

    Eligible properties must have their documentation reviewed and approved
    by administrators (either an approved Ghana Card on file for the landlord,
    or approved listing-specific documents).
    """
    minute_epoch = int(time.time() // 60)
    cache_key = f"home_featured_4_epoch_{minute_epoch}"

    cached_properties = cache.get(cache_key)
    if cached_properties is not None:
        return cached_properties

    verified_docs_q = (
        Q(
            landlord_documents__verification_status=LandlordDocument.VerificationStatus.VERIFIED
        )
        | Q(
            landlord__documents__document_type=LandlordDocument.DocumentType.NATIONAL_ID,
            landlord__documents__verification_status=LandlordDocument.VerificationStatus.VERIFIED,
        )
    )

    qs = list(
        Property.objects.filter(
            verified_docs_q,
            publication_status=Property.PublicationStatus.PUBLISHED,
            verification_status=Property.VerificationStatus.VERIFIED,
            is_available=True,
        )
        .distinct()
        .select_related("region", "district", "town", "area")
        .prefetch_related("amenities", "media")
    )

    if qs:
        # Seed pseudo-random generator with the 1-minute epoch so results rotate
        # synchronously across all workers/containers every 60 seconds
        rnd = random.Random(minute_epoch)
        selected = rnd.sample(qs, min(limit, len(qs)))
    else:
        selected = []

    # Cache for 65s so it covers the 60s lifecycle smoothly
    cache.set(cache_key, selected, timeout=65)
    return selected


def home(request):
    """
    Home page view.
    Renders 4 featured properties reshuffled every 1 minute.
    Only properties with admin-reviewed & approved documentation are listed.
    """
    hero_filters = {
        "q": request.GET.get("q", "").strip(),
        "region": request.GET.get("region", "").strip(),
        "room_type": request.GET.get("room_type", "").strip(),
        "min_price": request.GET.get("min_price", "").strip(),
        "max_price": request.GET.get("max_price", "").strip(),
    }

    has_search_query = any(bool(v) for v in hero_filters.values())

    if has_search_query:
        verified_docs_q = (
            Q(
                landlord_documents__verification_status=LandlordDocument.VerificationStatus.VERIFIED
            )
            | Q(
                landlord__documents__document_type=LandlordDocument.DocumentType.NATIONAL_ID,
                landlord__documents__verification_status=LandlordDocument.VerificationStatus.VERIFIED,
            )
        )
        qs = Property.objects.filter(
            verified_docs_q,
            publication_status=Property.PublicationStatus.PUBLISHED,
            verification_status=Property.VerificationStatus.VERIFIED,
            is_available=True,
        ).distinct().select_related("region", "district", "town", "area").prefetch_related("amenities", "media")
        properties = list(_apply_filters(qs, hero_filters)[:4])
    else:
        properties = get_shuffled_featured_properties(limit=4)

    regions = Region.objects.all().order_by("name")
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


def featured_properties_api(request):
    """
    Lightweight endpoint returning the 4 featured properties partial for
    live 1-minute client-side dynamic reshuffling.
    """
    properties = get_shuffled_featured_properties(limit=4)
    return render(
        request,
        'home_finder/partials/_featured_properties_cards.html',
        {
            "properties": properties,
            "request": request,
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
      - `total_count` : total matching properties (pre-pagination)

    This queryset intentionally does NOT filter by publication_status,
    verification_status, or is_available — all properties in the database
    are visible so visitors can browse the full catalogue.
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

    # Build the base queryset — ALL properties, no status gate
    qs = Property.objects.all().select_related(
        "region", "district", "town", "area", "landlord"
    ).prefetch_related("amenities", "media")

    qs = _apply_filters(qs, filters)
    qs = qs.order_by("-created_at")

    # Per-page selector: allow 12 / 24 / 48; default 12
    try:
        per_page = int(request.GET.get("per_page", 12))
        if per_page not in (12, 24, 48):
            per_page = 12
    except (TypeError, ValueError):
        per_page = 12

    total_count = qs.count()
    paginator = Paginator(qs, per_page)
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
        "total_count": total_count,
        "per_page": per_page,
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



from .forms import PropertyTourBookingForm


def get_property_detail(request, slug):
    property_obj = get_property_by_slug(slug=slug)
    
    if property_obj:
        from django.db.models import F
        from apps.home_finder.models import Property
        
        viewed_cookie_name = f'viewed_property_{property_obj.id}'
        if not request.COOKIES.get(viewed_cookie_name):
            # Only increment if the cookie is not present
            Property.objects.filter(id=property_obj.id).update(views_count=F("views_count") + 1)
            
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

    initial_data = {}
    if request.user.is_authenticated:
        initial_data = {
            'name': getattr(request.user, 'full_name', ''),
            'email': getattr(request.user, 'email', ''),
            'phone': getattr(request.user, 'phone_number', ''),
        }
    tour_form = PropertyTourBookingForm(initial=initial_data)

    response = render(request, 'home_finder/property_detail.html', {
        'property': property_obj,
        'has_expressed_interest': has_expressed_interest,
        'tour_form': tour_form,
    })
    
    if property_obj and not request.COOKIES.get(viewed_cookie_name):
        response.set_cookie(viewed_cookie_name, 'true', max_age=86400) # 24 hours
        
    return response


@require_POST
def book_property_tour(request, slug):
    """Allows both authenticated tenants and unauthenticated guests to schedule a property viewing tour."""
    property_obj = get_object_or_404(
        Property,
        slug=slug,
    )

    form = PropertyTourBookingForm(request.POST)
    if form.is_valid():
        preferred_date = form.cleaned_data["preferred_date"]
        preferred_time = form.cleaned_data["preferred_time"]
        notes = form.cleaned_data.get("notes", "")

        from apps.tenant.models import ViewingRequest
        from apps.landloards.tasks import notify_landlord_viewing_request_created_task

        if request.user.is_authenticated and request.user.role == request.user.Role.TENANT:
            tenant = request.user
            guest_name = ""
            guest_email = ""
            guest_phone = ""
        else:
            tenant = None
            guest_name = form.cleaned_data["name"]
            guest_email = form.cleaned_data["email"]
            guest_phone = form.cleaned_data["phone"]

        viewing_request = ViewingRequest.objects.create(
            property=property_obj,
            tenant=tenant,
            guest_name=guest_name,
            guest_email=guest_email,
            guest_phone=guest_phone,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            notes=notes,
            status=ViewingRequest.Status.PENDING,
        )

        # Dispatch background notification to landlord
        notify_landlord_viewing_request_created_task.delay(str(viewing_request.pk))

        messages.success(
            request,
            f"Viewing request for \"{property_obj.title}\" booked successfully! The landlord has been notified and will contact you."
        )
        return redirect("home_finder:property_detail", slug=slug)
    else:
        has_expressed_interest = False
        if request.user.is_authenticated and request.user.role == request.user.Role.TENANT:
            has_expressed_interest = PropertyInterest.objects.filter(
                property=property_obj,
                tenant=request.user,
            ).exists()

        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field.replace('_', ' ').title()}: {error}")

        return render(request, "home_finder/property_detail.html", {
            "property": property_obj,
            "has_expressed_interest": has_expressed_interest,
            "tour_form": form,
        })



@login_required
@require_POST
def express_property_interest(request, slug):
    """Let a tenant opt in to contact from the owner of a listing."""
    if request.user.role != request.user.Role.TENANT:
        messages.error(request, "Only tenant accounts can register interest in a property.")
        return redirect('home_finder:property_detail', slug=slug)

    # Use the same loose gate as the detail page (property's own status
    # flags only — no landlord-doc verification requirement).
    property_obj = get_property_by_slug(slug=slug)
    if property_obj is None:
        raise Http404("Property not found or not currently available.")
    _, created = PropertyInterest.objects.get_or_create(
        property=property_obj,
        tenant=request.user,
    )
    if created:
        messages.success(request, "Your interest has been shared with the property owner.")
    else:
        messages.info(request, "You have already registered your interest in this property.")
    return redirect('home_finder:property_detail', slug=slug)


def about(request):
    """About page for VacantHommie platform."""
    total_properties = Property.objects.count()
    verified_properties = Property.objects.filter(
        verification_status=Property.VerificationStatus.VERIFIED
    ).count()
    regions_count = Region.objects.count()

    return render(request, 'home_finder/about.html', {
        'total_properties': total_properties,
        'verified_properties': verified_properties,
        'regions_count': regions_count,
    })


def how_it_works(request):
    """How It Works page detailing step-by-step processes for tenants and landlords."""
    return render(request, 'home_finder/how_it_works.html')


def contact(request):
    """Contact us page with inquiry submission handling."""
    from .forms import ContactForm
    import logging
    from django.conf import settings
    from django.core.mail import send_mail

    logger = logging.getLogger(__name__)

    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            email = form.cleaned_data['email']
            phone = form.cleaned_data.get('phone', '')
            subject = form.cleaned_data['subject']
            message_text = form.cleaned_data['message']

            # Attempt sending an email notification to site admin/support
            try:
                subject_display = dict(ContactForm.SUBJECT_CHOICES).get(subject, subject)
                email_body = (
                    f"New Contact Inquiry from VacantHommie Website\n"
                    f"--------------------------------------------\n"
                    f"Name: {name}\n"
                    f"Email: {email}\n"
                    f"Phone: {phone or 'Not provided'}\n"
                    f"Subject: {subject_display}\n\n"
                    f"Message:\n{message_text}\n"
                )
                from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@vacanthommie.com')
                recipient_list = [from_email]

                send_mail(
                    subject=f"[VacantHommie Contact] {subject_display} from {name}",
                    message=email_body,
                    from_email=from_email,
                    recipient_list=recipient_list,
                    fail_silently=True,
                )
            except Exception as e:
                logger.warning(f"Could not send contact email: {e}")

            messages.success(
                request,
                f"Thank you, {name}! Your message has been received. Our team will get back to you shortly."
            )
            return redirect('home_finder:contact')
        else:
            messages.error(request, "Please correct the errors in the form below.")
    else:
        initial_data = {}
        if request.user.is_authenticated:
            initial_data['email'] = request.user.email
            if hasattr(request.user, 'first_name') and request.user.first_name:
                initial_data['name'] = f"{request.user.first_name} {getattr(request.user, 'last_name', '')}".strip()
            elif hasattr(request.user, 'get_full_name'):
                initial_data['name'] = request.user.get_full_name()
            if hasattr(request.user, 'phone_number') and request.user.phone_number:
                initial_data['phone'] = str(request.user.phone_number)
        form = ContactForm(initial=initial_data)

    return render(request, 'home_finder/contact.html', {
        'form': form,
    })

