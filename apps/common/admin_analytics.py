import json
from datetime import timedelta
from decimal import Decimal
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.account.models import User
from apps.home_finder.models import Property
from apps.locations.models import Region
from apps.Subscription.models import LandlordSubscription
from apps.tenant.models import ViewingRequest


def get_admin_dashboard_context(request=None):
    now = timezone.now()

    # -------------------------------------------------------------------------
    # Parse Filter Parameters
    # -------------------------------------------------------------------------
    timeframe = 'all'
    selected_region = ''
    selected_property_status = 'all'

    if request and hasattr(request, 'GET'):
        timeframe = request.GET.get('timeframe', 'all').lower()
        selected_region = request.GET.get('region', '').strip()
        selected_property_status = request.GET.get('property_status', 'all').lower()

    # Determine start_date based on timeframe
    start_date = None
    if timeframe == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif timeframe == '7days':
        start_date = now - timedelta(days=7)
    elif timeframe == '30days':
        start_date = now - timedelta(days=30)
    elif timeframe == '90days':
        start_date = now - timedelta(days=90)
    elif timeframe == 'year':
        start_date = now - timedelta(days=365)

    is_filtered = bool(timeframe != 'all' or selected_region or selected_property_status != 'all')

    # Available regions for filter dropdown
    available_regions = list(Region.objects.all().order_by('name').values('id', 'name'))

    # Base QuerySets
    user_qs = User.objects.all()
    prop_qs = Property.objects.all()
    sub_qs = LandlordSubscription.objects.all()
    viewing_qs = ViewingRequest.objects.all()

    # Apply Region Filter
    if selected_region:
        try:
            prop_qs = prop_qs.filter(region_id=selected_region)
            viewing_qs = viewing_qs.filter(property__region_id=selected_region)
        except Exception:
            selected_region = ''

    # Apply Property Status Filter (for listing table and property counters)
    if selected_property_status in [Property.VerificationStatus.VERIFIED, Property.VerificationStatus.PENDING, Property.VerificationStatus.REJECTED]:
        prop_qs_filtered = prop_qs.filter(verification_status=selected_property_status)
    else:
        prop_qs_filtered = prop_qs

    # Apply Timeframe Filter
    if start_date:
        user_qs_timed = user_qs.filter(created_at__gte=start_date)
        prop_qs_timed = prop_qs_filtered.filter(created_at__gte=start_date)
        sub_qs_timed = sub_qs.filter(created_at__gte=start_date)
        viewing_qs_timed = viewing_qs.filter(created_at__gte=start_date)
    else:
        user_qs_timed = user_qs
        prop_qs_timed = prop_qs_filtered
        sub_qs_timed = sub_qs
        viewing_qs_timed = viewing_qs

    # -------------------------------------------------------------------------
    # 1. User Metrics
    # -------------------------------------------------------------------------
    total_users = user_qs_timed.count()
    total_active_users = user_qs.filter(is_active=True).count()
    total_tenants = user_qs_timed.filter(role=User.Role.TENANT).count()
    total_landlords = user_qs_timed.filter(role=User.Role.LANDLORD).count()
    total_admins = user_qs_timed.filter(
        models.Q(role=User.Role.ADMIN) | models.Q(is_superuser=True) | models.Q(is_staff=True)
    ).distinct().count()

    active_trials = User.objects.filter(
        role=User.Role.LANDLORD,
        trial_started=True,
        trial_end_date__gt=now
    ).count()

    # -------------------------------------------------------------------------
    # 2. Property Metrics
    # -------------------------------------------------------------------------
    total_properties = prop_qs_timed.count()
    approved_properties = prop_qs_timed.filter(
        verification_status=Property.VerificationStatus.VERIFIED
    ).count()
    pending_properties = prop_qs_timed.filter(
        verification_status=Property.VerificationStatus.PENDING
    ).count()
    rejected_properties = prop_qs_timed.filter(
        verification_status=Property.VerificationStatus.REJECTED
    ).count()
    published_properties = prop_qs_timed.filter(
        publication_status=Property.PublicationStatus.PUBLISHED
    ).count()
    total_views = prop_qs_timed.aggregate(total=models.Sum('views_count'))['total'] or 0

    # -------------------------------------------------------------------------
    # 3. Financial & Subscription Metrics
    # -------------------------------------------------------------------------
    successful_subs = sub_qs_timed.filter(status=LandlordSubscription.Status.SUCCESS)
    total_revenue = successful_subs.aggregate(total=models.Sum('plan__price'))['total'] or Decimal('0.00')
    active_subscriptions = sub_qs.filter(
        is_active=True,
        status=LandlordSubscription.Status.SUCCESS,
        end_date__gt=now
    ).count()
    pending_transactions = sub_qs_timed.filter(status=LandlordSubscription.Status.PENDING).count()
    failed_transactions = sub_qs_timed.filter(status=LandlordSubscription.Status.FAILED).count()

    # -------------------------------------------------------------------------
    # 4. Viewing Requests Metrics
    # -------------------------------------------------------------------------
    total_viewing_requests = viewing_qs_timed.count()
    pending_viewing_requests = viewing_qs_timed.filter(status=ViewingRequest.Status.PENDING).count()
    confirmed_viewing_requests = viewing_qs_timed.filter(status=ViewingRequest.Status.CONFIRMED).count()
    completed_viewing_requests = viewing_qs_timed.filter(status=ViewingRequest.Status.COMPLETED).count()
    cancelled_viewing_requests = viewing_qs_timed.filter(status=ViewingRequest.Status.CANCELLED).count()

    # -------------------------------------------------------------------------
    # 5. Chart Data: Monthly Revenue (Last 6 Months)
    # -------------------------------------------------------------------------
    revenue_labels = []
    revenue_data = []
    transactions_count_data = []

    for i in range(5, -1, -1):
        month_offset_date = now - timedelta(days=i * 30)
        month_start = month_offset_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        month_end = next_month - timedelta(microseconds=1)

        label = month_start.strftime("%b %Y")
        revenue_labels.append(label)

        monthly_subs = sub_qs.filter(
            status=LandlordSubscription.Status.SUCCESS,
            created_at__gte=month_start,
            created_at__lte=month_end
        )
        m_rev = monthly_subs.aggregate(total=models.Sum('plan__price'))['total'] or Decimal('0.00')
        revenue_data.append(float(m_rev))
        transactions_count_data.append(monthly_subs.count())

    # -------------------------------------------------------------------------
    # 6. Chart Data: Property Types Distribution
    # -------------------------------------------------------------------------
    room_types = Property.RoomType.choices
    property_type_labels = [label for _, label in room_types]
    property_type_data = [
        prop_qs_timed.filter(room_type=val).count()
        for val, _ in room_types
    ]

    # -------------------------------------------------------------------------
    # 7. Tables Data
    # -------------------------------------------------------------------------
    recent_transactions = sub_qs_timed.select_related('landlord', 'plan').order_by('-created_at')[:10]
    transaction_records = []
    for tx in recent_transactions:
        try:
            admin_url = reverse('admin:Subscription_landlordsubscription_change', args=[tx.pk])
        except Exception:
            admin_url = "#"
        transaction_records.append({
            'id': tx.id,
            'reference': tx.payment_reference or tx.idempotence_key or f"SUB-{str(tx.id)[:8]}",
            'landlord_name': tx.landlord.full_name or tx.landlord.email if tx.landlord else "Unknown",
            'landlord_email': tx.landlord.email if tx.landlord else "",
            'plan_name': tx.plan.name if tx.plan else "N/A",
            'amount': tx.plan.price if tx.plan else Decimal('0.00'),
            'status': tx.status,
            'is_active': tx.is_active,
            'created_at': tx.created_at,
            'start_date': tx.start_date,
            'end_date': tx.end_date,
            'admin_url': admin_url,
        })

    pending_property_list = prop_qs.filter(
        verification_status=Property.VerificationStatus.PENDING
    ).select_related('landlord', 'town', 'region').order_by('-created_at')[:8]

    pending_properties_records = []
    for prop in pending_property_list:
        try:
            admin_url = reverse('admin:home_finder_property_change', args=[prop.pk])
        except Exception:
            admin_url = "#"
        pending_properties_records.append({
            'id': prop.id,
            'reference_number': prop.reference_number,
            'title': prop.title,
            'landlord_name': prop.landlord.full_name if prop.landlord else "Unknown",
            'price': prop.price,
            'payment_period': prop.get_payment_period_display(),
            'room_type': prop.get_room_type_display(),
            'location': f"{prop.town.name}, {prop.region.name}" if prop.town and prop.region else "N/A",
            'created_at': prop.created_at,
            'admin_url': admin_url,
        })

    recent_viewings = viewing_qs_timed.select_related('tenant', 'property').order_by('-created_at')[:8]
    viewing_records = []
    for vr in recent_viewings:
        try:
            admin_url = reverse('admin:tenant_viewingrequest_change', args=[vr.pk])
        except Exception:
            admin_url = "#"
        viewing_records.append({
            'id': vr.id,
            'property_title': vr.property.title if vr.property else "N/A",
            'property_ref': vr.property.reference_number if vr.property else "",
            'requester_name': vr.requester_name,
            'requester_phone': vr.requester_phone,
            'preferred_date': vr.preferred_date,
            'preferred_time': vr.preferred_time,
            'status': vr.status,
            'created_at': vr.created_at,
            'admin_url': admin_url,
        })

    # -------------------------------------------------------------------------
    # 8. Package Context Payload
    # -------------------------------------------------------------------------
    return {
        # Active filter state
        'timeframe': timeframe,
        'selected_region': selected_region,
        'selected_property_status': selected_property_status,
        'is_filtered': is_filtered,
        'available_regions': available_regions,

        # Card Numbers
        'stats_total_users': total_users,
        'stats_total_active_users': total_active_users,
        'stats_total_tenants': total_tenants,
        'stats_total_landlords': total_landlords,
        'stats_total_admins': total_admins,
        'stats_active_trials': active_trials,

        'stats_total_properties': total_properties,
        'stats_approved_properties': approved_properties,
        'stats_pending_properties': pending_properties,
        'stats_rejected_properties': rejected_properties,
        'stats_published_properties': published_properties,
        'stats_total_views': total_views,

        'stats_total_revenue': total_revenue,
        'stats_active_subscriptions': active_subscriptions,
        'stats_pending_transactions': pending_transactions,
        'stats_failed_transactions': failed_transactions,

        'stats_total_viewing_requests': total_viewing_requests,
        'stats_pending_viewing_requests': pending_viewing_requests,
        'stats_confirmed_viewing_requests': confirmed_viewing_requests,
        'stats_completed_viewing_requests': completed_viewing_requests,
        'stats_cancelled_viewing_requests': cancelled_viewing_requests,

        # Chart JSON configs
        'chart_revenue_labels_json': json.dumps(revenue_labels),
        'chart_revenue_data_json': json.dumps(revenue_data),
        'chart_transactions_data_json': json.dumps(transactions_count_data),

        'chart_users_labels_json': json.dumps(['Tenants', 'Landlords', 'Admins']),
        'chart_users_data_json': json.dumps([total_tenants, total_landlords, total_admins]),

        'chart_property_status_labels_json': json.dumps(['Approved / Verified', 'Pending Verification', 'Rejected']),
        'chart_property_status_data_json': json.dumps([approved_properties, pending_properties, rejected_properties]),

        'chart_property_types_labels_json': json.dumps(property_type_labels),
        'chart_property_types_data_json': json.dumps(property_type_data),

        'chart_viewings_labels_json': json.dumps(['Pending', 'Confirmed', 'Completed', 'Cancelled']),
        'chart_viewings_data_json': json.dumps([
            pending_viewing_requests,
            confirmed_viewing_requests,
            completed_viewing_requests,
            cancelled_viewing_requests
        ]),

        # Tables
        'transaction_records': transaction_records,
        'pending_properties_records': pending_properties_records,
        'viewing_records': viewing_records,
    }
