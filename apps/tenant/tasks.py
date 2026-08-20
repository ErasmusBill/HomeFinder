"""
Celery tasks for the property-alert pipeline.

Two task types live here:

1. `match_and_dispatch_property_alerts_task(property_id)` — fires on
   `Property.post_save` (via `apps/home_finder/signals.py`) and on the
   hourly beat catchup. Gated on `settings.PROPERTY_ALERTS_ENABLED`.

2. `send_property_alert_email_task(notification_id)` — sends the email
   for a single in-app Notification. Kept as its own task so a slow /
   failing SMTP server doesn't block the matcher, and so Celery's retry
   behavior isolates transient mail failures from the rest of the
   pipeline.

The matcher / dispatcher itself lives in
`apps/tenant.services.property_alerts` so it's testable without Celery.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Shared email helper
# ---------------------------------------------------------------------------
# Mirrors `_send_email` in `apps/Subscription/tasks.py` so the two apps
# produce visually consistent transactional mail. Kept private to this
# module — the property-alert email is a single template, so we don't
# need the (subject, template_name, context, to_email) signature here.

def _send_property_alert_email(notification, property_obj, tenant):
    """Render + send the property-alert email for one tenant."""
    # Build a deep link to the property detail page. We use the slug
    # because that's the URL kwarg (`property/<slug:slug>/`). If the
    # property is later unpublished/deleted, `get_absolute_url` would
    # 404 — the in-app notification still works, the email just has a
    # dead link, which is fine.
    try:
        property_url = f"{settings.FRONTEND_URL}/property/{property_obj.slug}/"
    except Exception:  # pragma: no cover — defensive
        property_url = settings.FRONTEND_URL

    context = {
        "full_name": tenant.full_name,
        "property_title": property_obj.title,
        "property_location": (
            f"{property_obj.area.name}, {property_obj.district.name}, "
            f"{property_obj.region.name}"
        ),
        "property_price": f"GHS {property_obj.price:,.0f}",
        "property_room_type": property_obj.get_room_type_display(),
        "property_url": property_url,
        "notification_title": notification.title,
    }

    html_body = render_to_string("tenant/emails/property_alert.html", context)
    text_body = render_to_string("tenant/emails/property_alert.txt", context)

    email = EmailMultiAlternatives(
        subject=f"New match: {property_obj.title}",
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
        to=[tenant.email],
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=False)


# ---------------------------------------------------------------------------
# Per-property matcher / dispatcher
# ---------------------------------------------------------------------------

# Shared decorator options for every retryable task in this file.
_TASK_KWARGS = dict(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)


@shared_task(**_TASK_KWARGS)
def match_and_dispatch_property_alerts_task(self, property_id):
    """
    Match a single Property against active PropertyAlert rows and
    dispatch in-app + email notifications for every new match.

    Idempotency: the dispatcher's M2M dedup makes this safe to call
    multiple times for the same property. The hourly beat catchup
    deliberately re-runs it for recently-published properties; the
    `notified_properties` M2M prevents double-notification.
    """
    # Kill switch — see config/settings/base.py.
    if not getattr(settings, "PROPERTY_ALERTS_ENABLED", False):
        logger.debug(
            "match_and_dispatch_property_alerts_task: PROPERTY_ALERTS_ENABLED "
            "is False; skipping property %s.",
            property_id,
        )
        return {"skipped": True, "reason": "kill_switch"}

    # Imports are inside the task so module import stays cheap and we
    # don't pay for Django ORM at import time. Also avoids the
    # historical circular-import gotcha when both apps reference each
    # other's models.
    from apps.home_finder.models import Property
    from apps.tenant.services.property_alerts import (
        dispatch_alert_notifications,
        find_matching_alerts,
        is_property_alertable,
    )

    try:
        property_obj = (
            Property.objects
            .select_related("region", "district", "area", "town")
            .get(pk=property_id)
        )
    except Property.DoesNotExist:
        logger.warning(
            "match_and_dispatch_property_alerts_task: property %s no longer exists",
            property_id,
        )
        return {"matched": 0, "notified": 0, "skipped": 0}

    if not is_property_alertable(property_obj):
        logger.debug(
            "match_and_dispatch_property_alerts_task: property %s is not "
            "alertable (publication_status=%s is_available=%s).",
            property_id, property_obj.publication_status, property_obj.is_available,
        )
        return {"matched": 0, "notified": 0, "skipped": 0}

    matches = find_matching_alerts(property_obj)
    alert_ids = [str(a.pk) for a in matches]
    if not alert_ids:
        return {"matched": 0, "notified": 0, "skipped": 0}

    return dispatch_alert_notifications(property_obj, alert_ids)


# ---------------------------------------------------------------------------
# Per-notification email sender
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_property_alert_email_task(self, notification_id):
    """
    Send the email for a single in-app Notification created by
    `dispatch_alert_notifications`. Resolves the notification → tenant →
    property via FK hops and renders the email template.

    Kept separate from the matcher so a transient SMTP failure only
    retries this single email rather than re-running the entire match
    pipeline.
    """
    from apps.home_finder.models import Property
    from apps.notifications.models import Notification

    try:
        notification = Notification.objects.select_related("user").get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.warning(
            "send_property_alert_email_task: notification %s no longer exists",
            notification_id,
        )
        return

    tenant = notification.user
    if not tenant or not getattr(tenant, "email", None):
        logger.info(
            "send_property_alert_email_task: notification %s has no tenant "
            "or no email; skipping.",
            notification_id,
        )
        return

    # Per-tenant email opt-out (see User.email_property_alerts and
    # migration 0008_user_email_property_alerts). The in-app
    # Notification has already been created — that's still valuable
    # because the tenant is online and seeing matches is the primary
    # value. The email is the only thing this flag controls.
    if not getattr(tenant, "email_property_alerts", True):
        logger.info(
            "send_property_alert_email_task: tenant %s has opted out of "
            "property-alert emails; skipping email for notification %s.",
            tenant.pk, notification_id,
        )
        return

    # The GFK target may have been cleared if the property was deleted.
    # In that case the in-app notification is still valid as a
    # historical record, but the email would have nothing to link to —
    # skip the email but log it so ops can investigate.
    target = notification.target
    if target is None or not isinstance(target, Property):
        logger.info(
            "send_property_alert_email_task: notification %s has no property "
            "target; skipping email.",
            notification_id,
        )
        return

    try:
        _send_property_alert_email(notification, target, tenant)
        logger.info(
            "send_property_alert_email_task: sent property-alert email to %s "
            "for notification %s (property %s).",
            tenant.email, notification_id, target.pk,
        )
    except Exception as exc:
        logger.error(
            "send_property_alert_email_task: failed for notification %s: %s",
            notification_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Hourly beat catchup
# ---------------------------------------------------------------------------
# Safety net for two cases:
#   1. The post_save signal was lost (e.g. the worker was offline when
#      the landlord saved the property).
#   2. The pipeline was previously disabled (PROPERTY_ALERTS_ENABLED=False)
#      and was just turned on — we want to backfill alerts for any
#      properties published in the last 24h that haven't been matched.
#
# Both cases are handled by re-running the matcher against every
# property published in the last 24h; the M2M dedup means we only
# notify for genuinely new matches.

@shared_task
def property_alert_catchup_task():
    """
    Re-run the matcher for every property published in the last 24 hours
    that is still published and available. Runs hourly via
    CELERY_BEAT_SCHEDULE.

    The 24-hour window is the deliberate trade-off: a wider window (e.g.
    "since the pipeline was turned on") would risk replaying alerts for
    properties the tenant has already seen, while a narrower window (e.g.
    10 minutes) would miss anything the signal-handler dropped. 24h
    gives the beat task a fighting chance to catch *every* property
    before it scrolls out of a tenant's feed, while still being cheap.
    """
    if not getattr(settings, "PROPERTY_ALERTS_ENABLED", False):
        logger.debug(
            "property_alert_catchup_task: PROPERTY_ALERTS_ENABLED is False; "
            "skipping catchup run."
        )
        return 0

    from apps.home_finder.models import Property

    cutoff = timezone.now() - timezone.timedelta(hours=24)
    property_ids = list(
        Property.objects
        .filter(
            publication_status=Property.PublicationStatus.PUBLISHED,
            is_available=True,
            created_at__gte=cutoff,
        )
        .values_list("id", flat=True)
    )

    queued = 0
    for pid in property_ids:
        match_and_dispatch_property_alerts_task.delay(str(pid))
        queued += 1

    logger.info(
        "property_alert_catchup_task: queued %d property(s) for re-matching "
        "(published in the last 24h).",
        queued,
    )
    return queued


# ---------------------------------------------------------------------------
# Viewing-request retention sweeper
# ---------------------------------------------------------------------------
# Hard-deletes viewing requests that have been sitting in a terminal
# state (cancelled or completed) for longer than
# ``settings.VIEWING_REQUEST_RETENTION_DAYS``. Runs once a day via
# ``CELERY_BEAT_SCHEDULE['purge-stale-viewing-requests']`` in
# ``config/settings/base.py``.
#
# Why hard delete?
# ----------------
# The ViewingRequest model already has a ``status`` column (cancelled /
# completed), so the row has zero analytical value once it leaves the
# tenant's active working set. Hard-deleting keeps:
#   * the tenant's dashboard counts honest (no ghost rows inflating
#     "Total Requests" forever)
#   * the per-tenant / per-landlord caches small
#   * the database from accumulating junk
#
# In-app notifications whose ``target`` is the underlying ``Property``
# are intentionally left alone - they reference the Property, not the
# ViewingRequest, and they remain a useful historical record on the
# listing.

@shared_task(name="tenant.tasks.purge_stale_viewing_requests_task")
def purge_stale_viewing_requests_task():
    """
    Delete viewing requests in terminal states (cancelled / completed)
    whose ``updated_at`` is older than
    ``settings.VIEWING_REQUEST_RETENTION_DAYS``.

    Returns a dict summarising how many rows were deleted and broken
    down by status - useful for the Celery worker logs / Flower.
    """
    from django.conf import settings as _settings
    from django.db.models import Count as _Count
    from apps.tenant.models import ViewingRequest as _VR

    retention_days = getattr(
        _settings, "VIEWING_REQUEST_RETENTION_DAYS", 30,
    )
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)

    terminal_statuses = [
        _VR.Status.CANCELLED,
        _VR.Status.COMPLETED,
    ]

    # Snapshot the affected landlord + tenant IDs *before* the delete so
    # we can invalidate their caches in one pass. We do this with two
    # cheap .values_list() queries (no full row hydration) and keep the
    # whole sweep to a constant number of queries regardless of how
    # many rows are being deleted.
    base_filter_qs = _VR.objects.filter(
        status__in=terminal_statuses, updated_at__lt=cutoff,
    )
    affected_landlord_ids = set(
        base_filter_qs.values_list("property__landlord_id", flat=True)
    )
    affected_tenant_ids = set(
        base_filter_qs.values_list("tenant_id", flat=True)
    )

    # Per-status counts for the summary log line.
    per_status_pairs = (
        base_filter_qs
        .values("status")
        .annotate(count=_Count("id"))
        .values_list("status", "count")
    )
    per_status_counts = {status: count for status, count in per_status_pairs}

    # The actual delete. Returns (total_deleted, rows_by_model).
    deleted_total, _ = base_filter_qs.delete()

    # Invalidate caches *only* if we actually deleted something.
    if deleted_total:
        try:
            from apps.landloards.selectors import (
                invalidate_landlord_viewing_requests_cache,
            )
            for landlord_id in affected_landlord_ids:
                if landlord_id is None:
                    continue
                invalidate_landlord_viewing_requests_cache(landlord_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "purge_stale_viewing_requests_task: failed to invalidate "
                "landlord caches: %s",
                exc,
            )

        # Drop the per-tenant viewing-requests cache so the tenant
        # dashboard and the watching list refetch on the next request
        # and reflect the smaller set.
        from apps.tenant.selectors import get_viewing_requests_cache_key
        cache.delete_many([
            get_viewing_requests_cache_key(tenant_id)
            for tenant_id in affected_tenant_ids
            if tenant_id is not None
        ])

    summary = {
        "deleted": deleted_total,
        "retention_days": retention_days,
        "by_status": per_status_counts,
        "affected_landlords": len(
            lid for lid in affected_landlord_ids if lid is not None
        ),
        "affected_tenants": len(affected_tenant_ids),
    }
    logger.info(
        "purge_stale_viewing_requests_task: removed %d stale viewing "
        "request(s) (retention=%d days, by_status=%s, landlords=%d, "
        "tenants=%d).",
        deleted_total, retention_days, per_status_counts,
        summary["affected_landlords"], summary["affected_tenants"],
    )
    return summary
