from decimal import Decimal, InvalidOperation

from apps.home_finder.models import Property


def search_properties(
    location=None,
    room_type=None,
    min_price=None,
    max_price=None,
    bedrooms=None,
    bathrooms=None,
    is_furnished=None,
    payment_period=None,
    limit=5,
):
    """
    Search published, verified and available VacantHommie properties.
    """

    queryset = (
        Property.objects
        .filter(
            publication_status=Property.PublicationStatus.PUBLISHED,
            verification_status=Property.VerificationStatus.VERIFIED,
            is_available=True,
        )
        .select_related(
            "region",
            "district",
            "town",
            "area",
            "landlord",
        )
        .prefetch_related("amenities")
    )

    # Location can match any level of our location hierarchy.
    if location:
        location = location.strip()

        from django.db.models import Q

        queryset = queryset.filter(
            Q(region__name__icontains=location)
            | Q(district__name__icontains=location)
            | Q(town__name__icontains=location)
            | Q(area__name__icontains=location)
        )

    if room_type:
        queryset = queryset.filter(
            room_type=room_type
        )

    if bedrooms is not None:
        queryset = queryset.filter(
            bedrooms=bedrooms
        )

    if bathrooms is not None:
        queryset = queryset.filter(
            bathrooms=bathrooms
        )

    if is_furnished is not None:
        queryset = queryset.filter(
            is_furnished=is_furnished
        )

    if payment_period:
        queryset = queryset.filter(
            payment_period=payment_period
        )

    if min_price is not None:
        try:
            queryset = queryset.filter(
                price__gte=Decimal(str(min_price))
            )
        except (InvalidOperation, ValueError, TypeError):
            pass

    if max_price is not None:
        try:
            queryset = queryset.filter(
                price__lte=Decimal(str(max_price))
            )
        except (InvalidOperation, ValueError, TypeError):
            pass

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 5

    limit = max(1, min(limit, 10))

    properties = queryset.order_by("-created_at")[:limit]

    return [
        {
            "id": str(property.id),
            "reference_number": property.reference_number,
            "title": property.title,
            "price": str(property.price),
            "payment_period": property.payment_period,
            "room_type": property.room_type,
            "bedrooms": property.bedrooms,
            "bathrooms": property.bathrooms,
            "toilets": property.toilets,
            "parking_spaces": property.parking_spaces,
            "is_furnished": property.is_furnished,
            "available_from": (
                property.available_from.isoformat()
                if property.available_from
                else None
            ),
            "cover_image_url": property.cover_image.url if property.cover_image else "",
            "detail_url": f"/property/{property.slug}/",
            "location": {
                "region": property.region.name,
                "district": property.district.name,
                "town": property.town.name,
                "area": property.area.name,
            },
            "amenities": [
                amenity.name
                for amenity in property.amenities.all()
            ],
        }
        for property in properties
    ]