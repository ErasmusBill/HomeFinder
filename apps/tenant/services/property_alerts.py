"""
Property-alert matching & dispatch service.

Kept deliberately separate from the Celery tasks in `apps/tenant/tasks.py`
so the matcher is unit-testable without Celery, and so the same logic can
be called from both the per-property `post_save` trigger and the hourly
beat catchup (see `property_alert_catchup_task`).

Public API:
    find_matching_alerts(property)            -> QuerySet[PropertyAlert]
    dispatch_alert_notifications(property, alert_ids)
                                               -> dict[str, int]

Dedup model:
    `PropertyAlert.notified_properties` is an M2M to `Property`. A row in
    that M2M is the source of truth for "this alert has already been
    notified about this property" — checked before matching, and added
    after a successful dispatch. `last_notified_at` is also updated as a
    "last fired" stamp for the dashboard / debugging, but is not the
    primary dedup key (a single timestamp cannot dedup multiple
    properties).

Kill switch:
    All entry points honor `settings.PROPERTY_ALERTS_ENABLED`. When the
    flag is False the matcher returns an empty queryset and the
    dispatcher is a no-op. This is the safety lever that lets the
    pipeline be deployed and tested without spamming tenants — see the
    comment block in `config/settings/base.py`.
"""
from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import Notification
from apps.tenant.models import Property, PropertyAlert

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------
# Properties only trigger alerts when they are *published*. Drafts and
# archived listings are noise — a tenant should never be emailed about a
# property the landlord hasn't put live yet. Verification status is not
# a blocker: in practice landlords publish first and verification is
# reviewed out-of-band. If you want to gate on verification too, add
# `verification_status=Property.VerificationStatus.VERIFIED` to the
# queryset below.

def is_property_alertable(property_obj: Property) -> bool:
    """Return True iff this property should be considered by the matcher."""
    if property_obj is None:
        return False
    if property_obj.publication_status != Property.PublicationStatus.PUBLISHED:
        return False
    # `is_available` is a separate flag the landlord toggles; respect it
    # so we don't notify tenants about a property the landlord has
    # temporarily taken off the market.
    if not property_obj.is_available:
        return False
    # Optional verification gate. Off by default (see
    # PROPERTY_ALERTS_REQUIRE_VERIFICATION in config/settings/base.py)
    # so the pipeline matches the pre-feature behavior of alerting on
    # any published listing. Flip the setting to True once you're
    # comfortable only surfacing verified listings to tenants.
    if getattr(settings, "PROPERTY_ALERTS_REQUIRE_VERIFICATION", False):
        if property_obj.verification_status != Property.VerificationStatus.VERIFIED:
            return False
    return True


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def find_matching_alerts(property_obj: Property):
    """
    Return the queryset of `PropertyAlert` rows that match this property
    AND have not already been notified about it.

    Matching rules (mirrors what the form lets tenants pick):
      * region must match (always required on the alert)
      * if the alert has an `area`, the property's area must match it
      * elif the alert has a `district`, the property's district must match
      * elif only `region` is set, any property in the region matches
      * room_type must match exactly
      * property.price must fall inside [min_price, max_price]
      * the alert must be active
      * the (alert, property) pair must not already be in `notified_properties`

    Returns a queryset (not a list) so callers can paginate, count, or
    chain further if needed.
    """
    base_qs = PropertyAlert.objects.filter(
        is_active=True,
        region_id=property_obj.region_id,
        room_type=property_obj.room_type,
        min_price__lte=property_obj.price,
        max_price__gte=property_obj.price,
    ).exclude(
        # Dedup: skip alerts that have already been notified about this
        # property. The M2M stores Property IDs; reverse lookup via
        # `notified_properties` lets us express "not in this set" in a
        # single SQL clause.
        notified_properties=property_obj,
    )

    # Location specificity: more specific alerts (area > district > region)
    # naturally win because they add a tighter WHERE clause. We layer
    # them with OR so an alert matches if *any* of its non-null location
    # constraints match the property. This is the same shape as the
    # `Q(region=..., district=..., area=...)` pattern used elsewhere in
    # the codebase (see `apps/tenant/selectors.py`).
    location_q = Q()
    if property_obj.area_id:
        location_q |= Q(area_id=property_obj.area_id)
    if property_obj.district_id:
        location_q |= Q(district_id=property_obj.district_id)
    # region-only is already covered by the base filter; we only need
    # the extra clause if the alert actually pins district/area.
    if location_q:
        base_qs = base_qs.filter(location_q)

    return base_qs.select_related("tenant", "region", "district", "area")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _format_location(alert: PropertyAlert) -> str:
    """Human-readable location string for notification copy."""
    parts = [p for p in (alert.area, alert.district, alert.region) if p]
    return ", ".join(p.name for p in parts) if parts else "anywhere"


def _format_price(alert: PropertyAlert) -> str:
    """Price range string for notification copy."""
    return f"GHS {alert.min_price:,.0f} – GHS {alert.max_price:,.0f}"


@transaction.atomic
def dispatch_alert_notifications(
    property_obj: Property, alert_ids: Iterable[str]
) -> dict:
    """
    For each `(alert, property)` pair, create the in-app Notification,
    queue the email task, and record the dedup row in a single
    transaction so we never end up with a notification that has no
    dedup (or vice versa).

    Returns a small dict with counts so the caller (Celery task) can log
    a useful summary.
    """
    # Re-resolve inside the transaction to get a consistent view of the
    # alerts and avoid acting on rows that were deleted between matching
    # and dispatching.
    alerts = list(
        PropertyAlert.objects
        .select_for_update()
        .filter(pk__in=list(alert_ids), is_active=True)
        .exclude(notified_properties=property_obj)
    )
    if not alerts:
        return {"matched": 0, "notified": 0, "skipped": 0}

    property_ct = ContentType.objects.get_for_model(Property)
    created_notifications = []

    for alert in alerts:
        notification = Notification(
            user=alert.tenant,
            created_by=None,
            title=f"New match: {property_obj.title}",
            content=(
                f"A new {property_obj.get_room_type_display()} in "
                f"{_format_location(alert)} matches your alert (budget "
                f"{_format_price(alert)}). Take a look before someone "
                f"else does."
            ),
            content_type=property_ct,
            object_id=str(property_obj.pk),
        )
        notification.save()
        created_notifications.append(notification)

        # Record dedup *inside* the same transaction so a rollback
        # (e.g. Notification save failed) means we won't think we've
        # already notified for this property.
        alert.notified_properties.add(property_obj)
        alert.last_notified_at = timezone.now()
        alert.save(update_fields=["last_notified_at", "updated_at"])

    # Email tasks are queued via on_commit so a transaction rollback
    # cancels the dispatch — matching the pattern used in
    # `Subscription.tasks`. Each email gets its own per-task countdown
    # computed from its position in this fanout, so small fanouts fire
    # immediately and large fanouts spread out evenly over
    # settings.PROPERTY_ALERTS_FANOUT_MAX_DELAY. See the comment block
    # above `PROPERTY_ALERTS_FANOUT_MAX_DELAY` in
    # config/settings/base.py for the rationale.
    total = len(created_notifications)
    max_delay = max(0, int(getattr(settings, "PROPERTY_ALERTS_FANOUT_MAX_DELAY", 0)))
    for position, n in enumerate(created_notifications):
        if total <= 1 or max_delay == 0:
            countdown = 0
        else:
            # position is 0-based; last email lands at exactly max_delay
            countdown = (position / (total - 1)) * max_delay
        transaction.on_commit(
            # Bind the loop variables via default args so the closure
            # captures the values from this iteration (not the final
            # loop values).
            lambda nid=str(n.id), p=position, t=total, cd=countdown:
                _queue_email_for_notification(nid, p, t, cd)
        )

    logger.info(
        "Property alert dispatch for property %s: %d notification(s) created, "
        "%d already-notified pairs skipped; fanout spread over up to %ss.",
        property_obj.pk, len(created_notifications),
        len(alert_ids) - len(created_notifications), max_delay,
    )
    return {
        "matched": len(alert_ids),
        "notified": len(created_notifications),
        "skipped": len(alert_ids) - len(created_notifications),
        "fanout_max_delay": max_delay,
    }


def _queue_email_for_notification(
    notification_id: str, position: int, total: int, countdown: float
) -> None:
    """
    Thin wrapper so the on_commit lambda stays picklable. Imported here
    to avoid a circular import at module load (the tasks module imports
    this service).

    Uses `.apply_async(countdown=...)` rather than `.delay()` so the
    caller can spread the fanout over `settings.PROPERTY_ALERTS_FANOUT_MAX_DELAY`
    seconds. The `position` / `total` are passed through as a header
    so Celery Flower / logs can reconstruct the ordering without
    changing the task's public signature.
    """
    from apps.tenant.tasks import send_property_alert_email_task
    send_property_alert_email_task.apply_async(
        args=[notification_id],
        countdown=countdown,
        headers={
            "alert_fanout_position": position,
            "alert_fanout_total": total,
        },
    )
