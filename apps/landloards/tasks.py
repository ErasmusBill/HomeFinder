import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Q

logger = logging.getLogger(__name__)
User = get_user_model()


def _admin_recipient_q():
    """
    Q object matching admin users: superusers, staff, or role='admin'.
    Centralized so the policy is easy to tweak in one place.
    """
    admin_role = getattr(User.Role, "ADMIN", "admin")
    return Q(is_superuser=True) | Q(is_staff=True) | Q(role=admin_role)


@shared_task(name="landloards.notify_admins_property_created", bind=True, max_retries=3)
def notify_admins_property_created_task(self, property_id):
    """
    Background task that emails all admin / superuser accounts when a landlord
    creates a new property, so they can review and verify it.

    Args:
        property_id: The UUID of the newly created Property instance.
    """
    # Local import to avoid circular imports between apps
    from apps.home_finder.models import Property

    try:
        property_obj = (
            Property.objects
            .select_related("landlord", "region", "district", "town", "area")
            .get(pk=property_id)
        )
    except Property.DoesNotExist:
        logger.warning(
            "notify_admins_property_created_task: Property %s no longer exists; skipping email.",
            property_id,
        )
        return

    # Build the recipient list: active superusers + any user flagged as admin
    admin_emails = list(
        User.objects.filter(is_active=True)
        .filter(_admin_recipient_q())
        .values_list("email", flat=True)
    )
    # Drop empty / None values just in case
    admin_emails = [e for e in admin_emails if e]

    if not admin_emails:
        logger.info(
            "notify_admins_property_created_task: No active admin/superuser emails found; "
            "skipping notification for property %s.",
            property_id,
        )
        return

    landlord_name = (
        property_obj.landlord.full_name
        if property_obj.landlord_id and getattr(property_obj, "landlord", None)
        else "Unknown landlord"
    )
    landlord_email = getattr(getattr(property_obj, "landlord", None), "email", "N/A")

    location = (
        f"{property_obj.area}, {property_obj.town}, "
        f"{property_obj.district}, {property_obj.region}"
    )

    subject = f"[Action Required] New property pending verification: {property_obj.title}"

    message = (
        f"Hello Admin,\n\n"
        f"A new property has just been created and is awaiting verification.\n\n"
        f"Details:\n"
        f"  - Title: {property_obj.title}\n"
        f"  - Reference: {property_obj.reference_number}\n"
        f"  - Landlord: {landlord_name}\n"
        f"  - Landlord email: {landlord_email}\n"
        f"  - Price: {property_obj.price} ({property_obj.get_payment_period_display()})\n"
        f"  - Room type: {property_obj.get_room_type_display()}\n"
        f"  - Location: {location}\n"
        f"  - Verification status: {property_obj.get_verification_status_display()}\n"
        f"  - Publication status: {property_obj.get_publication_status_display()}\n\n"
        f"Please log in to the admin dashboard to review and verify this property.\n\n"
        f"Django admin link: /admin/home_finder/property/{property_obj.id}/change/\n\n"
        f"Automated notification from Vacant Hommie."
    )

    try:
        send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
            admin_emails,
            fail_silently=False,
        )
        logger.info(
            "notify_admins_property_created_task: Notification sent to %d admin(s) for property %s.",
            len(admin_emails),
            property_id,
        )
    except Exception as exc:
        logger.error(
            "notify_admins_property_created_task: Failed to send admin notification for "
            "property %s: %s",
            property_id,
            exc,
        )
        # Retry up to 3 times with a 60s backoff if the SMTP server hiccups
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="landloards.notify_landlord_property_verified", bind=True, max_retries=3)
def notify_landlord_property_verified_task(self, property_id, previous_status=None):
    """
    Background task that emails the landlord when the verification status of
    one of their properties changes (typically: pending -> verified, or
    pending -> rejected). The full new status is read from the DB; the
    ``previous_status`` argument is only used to decide whether the status
    actually changed (and to suppress no-op emails if it didn't).

    Args:
        property_id: The UUID of the Property whose status changed.
        previous_status: The verification_status value before the save,
            e.g. "pending". If it equals the current value we skip the email.
    """
    # Local import to avoid circular imports between apps
    from apps.home_finder.models import Property

    try:
        property_obj = (
            Property.objects
            .select_related("landlord")
            .get(pk=property_id)
        )
    except Property.DoesNotExist:
        logger.warning(
            "notify_landlord_property_verified_task: Property %s no longer exists; "
            "skipping email.",
            property_id,
        )
        return

    landlord = getattr(property_obj, "landlord", None)
    landlord_email = getattr(landlord, "email", None) if landlord else None

    if not landlord_email:
        logger.info(
            "notify_landlord_property_verified_task: Property %s has no landlord email; "
            "skipping notification.",
            property_id,
        )
        return

    new_status = property_obj.verification_status
    if previous_status is not None and previous_status == new_status:
        # No actual change — nothing to notify about.
        logger.info(
            "notify_landlord_property_verified_task: Status unchanged for property %s "
            "(%s); skipping email.",
            property_id,
            new_status,
        )
        return

    status_display = property_obj.get_verification_status_display()

    # 1. In-App Notification
    try:
        from django.contrib.contenttypes.models import ContentType
        from apps.notifications.models import Notification
        property_ct = ContentType.objects.get_for_model(Property)

        if new_status == Property.VerificationStatus.VERIFIED:
            notif_title = f"Property Approved: {property_obj.title}"
            notif_content = (
                f"Great news! Your property listing \"{property_obj.title}\" (Ref: {property_obj.reference_number}) "
                f"has been approved and verified by our team. It is now eligible for public viewing by tenants."
            )
        elif new_status == Property.VerificationStatus.REJECTED:
            notif_title = f"Property Not Approved: {property_obj.title}"
            notif_content = (
                f"Your property listing \"{property_obj.title}\" (Ref: {property_obj.reference_number}) "
                f"could not be verified at this time. Please check your listing details and supporting documents, then update your submission."
            )
        else:
            notif_title = None

        if notif_title and landlord:
            Notification.objects.create(
                user=landlord,
                created_by=None,
                title=notif_title,
                content=notif_content,
                content_type=property_ct,
                object_id=str(property_obj.id),
            )
    except Exception as exc:
        logger.error(
            "notify_landlord_property_verified_task: Failed to create in-app notification for property %s: %s",
            property_id,
            exc,
        )

    # 2. Email Notification
    if new_status == Property.VerificationStatus.VERIFIED:
        subject = f"Your property has been approved: {property_obj.title}"
        message = (
            f"Hi {landlord.full_name},\n\n"
            f"Great news! Your property listing '{property_obj.title}' has been reviewed and approved by our verification team.\n\n"
            f"Details:\n"
            f"  - Title: {property_obj.title}\n"
            f"  - Reference: {property_obj.reference_number}\n"
            f"  - Price: GHS {property_obj.price} / {property_obj.payment_period}\n"
            f"  - Location: {property_obj.area}, {property_obj.town}\n"
            f"  - Verification status: Approved / Verified\n\n"
            f"Your listing is now verified and eligible to be published and shown to prospective tenants.\n\n"
            f"Thank you for listing with VacantHommie!"
        )
    elif new_status == Property.VerificationStatus.REJECTED:
        subject = f"Your property verification was rejected: {property_obj.title}"
        message = (
            f"Hi {landlord.full_name},\n\n"
            f"Unfortunately, your property submission '{property_obj.title}' could not be verified at this time.\n\n"
            f"Details:\n"
            f"  - Title: {property_obj.title}\n"
            f"  - Reference: {property_obj.reference_number}\n"
            f"  - Verification status: {status_display}\n\n"
            f"Please review the listing, ensure correct details and supporting documents are provided, and update your submission.\n"
            f"If you believe this was a mistake, please contact our support team.\n\n"
            f"VacantHommie Support"
        )
    else:
        # Pending (or anything else) — no need to email the landlord for a
        # status we already notify them about on creation.
        logger.info(
            "notify_landlord_property_verified_task: Property %s status is '%s'; "
            "no landlord email sent.",
            property_id,
            new_status,
        )
        return

    try:
        send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
            [landlord_email],
            fail_silently=False,
        )
        logger.info(
            "notify_landlord_property_verified_task: Sent '%s' notification to landlord "
            "for property %s.",
            new_status,
            property_id,
        )
    except Exception as exc:
        logger.error(
            "notify_landlord_property_verified_task: Failed to send landlord notification "
            "for property %s: %s",
            property_id,
            exc,
        )
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="landloards.notify_landlord_document_reviewed", bind=True, max_retries=3)
def notify_landlord_document_reviewed_task(self, document_id, previous_status=None):
    """
    Background task that emails the landlord and creates an in-app notification when one of their uploaded
    supporting documents (LandlordDocument) is reviewed by an admin — i.e.
    its verification_status changes to 'verified' or 'rejected'.

    Args:
        document_id: The UUID of the LandlordDocument that was reviewed.
        previous_status: The verification_status value before the save.
            Used to suppress no-op emails when status didn't actually change.
    """
    # Local import to avoid circular imports between apps
    from apps.home_finder.models import LandlordDocument

    try:
        document = (
            LandlordDocument.objects
            .select_related("landlord", "property", "reviewed_by")
            .get(pk=document_id)
        )
    except LandlordDocument.DoesNotExist:
        logger.warning(
            "notify_landlord_document_reviewed_task: Document %s no longer exists; "
            "skipping email.",
            document_id,
        )
        return

    landlord = getattr(document, "landlord", None)
    landlord_email = getattr(landlord, "email", None) if landlord else None

    if not landlord_email:
        logger.info(
            "notify_landlord_document_reviewed_task: Document %s has no landlord email; "
            "skipping notification.",
            document_id,
        )
        return

    new_status = document.verification_status
    if previous_status is not None and previous_status == new_status:
        logger.info(
            "notify_landlord_document_reviewed_task: Status unchanged for document %s "
            "(%s); skipping email.",
            document_id,
            new_status,
        )
        return

    status_display = document.get_verification_status_display()
    doc_type_display = document.get_document_type_display()
    property_title = (
        document.property.title
        if getattr(document, "property", None)
        else "General Profile / Identity"
    )

    # 1. In-App Notification
    try:
        from django.contrib.contenttypes.models import ContentType
        from apps.notifications.models import Notification
        doc_ct = ContentType.objects.get_for_model(LandlordDocument)

        if new_status == LandlordDocument.VerificationStatus.VERIFIED:
            doc_notif_title = f"Document Approved: {doc_type_display}"
            doc_notif_content = (
                f"Your uploaded document \"{doc_type_display}\" ({property_title}) "
                f"has been approved and verified by administrators."
            )
        elif new_status == LandlordDocument.VerificationStatus.REJECTED:
            reason = (document.rejection_reason or "").strip()
            reason_suffix = f" Reason: {reason}" if reason else ""
            doc_notif_title = f"Document Needs Attention: {doc_type_display}"
            doc_notif_content = (
                f"Your document \"{doc_type_display}\" ({property_title}) was rejected.{reason_suffix} "
                f"Please upload a corrected document."
            )
        else:
            doc_notif_title = None

        if doc_notif_title and landlord:
            Notification.objects.create(
                user=landlord,
                created_by=None,
                title=doc_notif_title,
                content=doc_notif_content,
                content_type=doc_ct,
                object_id=str(document.id),
            )
    except Exception as exc:
        logger.error(
            "notify_landlord_document_reviewed_task: Failed to create in-app notification for doc %s: %s",
            document_id, exc,
        )

    # 2. Email Notification
    if new_status == LandlordDocument.VerificationStatus.VERIFIED:
        subject = f"Your document has been approved: {doc_type_display}"
        message = (
            f"Hi {landlord.full_name},\n\n"
            f"Your supporting document has been reviewed and approved.\n\n"
            f"Details:\n"
            f"  - Document type: {doc_type_display}\n"
            f"  - Linked property: {property_title}\n"
            f"  - Verification status: {status_display}\n\n"
            f"Thank you for keeping your documentation up to date.\n\n"
            f"VacantHommie"
        )
    elif new_status == LandlordDocument.VerificationStatus.REJECTED:
        reason = (document.rejection_reason or "").strip()
        reason_block = (
            f"\nReviewer notes:\n{reason}\n" if reason else ""
        )
        subject = f"Your document was rejected: {doc_type_display}"
        message = (
            f"Hi {landlord.full_name},\n\n"
            f"Unfortunately, your supporting document could not be approved.\n\n"
            f"Details:\n"
            f"  - Document type: {doc_type_display}\n"
            f"  - Linked property: {property_title}\n"
            f"  - Verification status: {status_display}\n"
            f"{reason_block}\n"
            f"Please upload a corrected document so we can complete your verification.\n\n"
            f"VacantHommie"
        )
    else:
        # Anything else (e.g. back to pending) — don't email.
        logger.info(
            "notify_landlord_document_reviewed_task: Document %s status is '%s'; "
            "no landlord email sent.",
            document_id,
            new_status,
        )
        return

    try:
        send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
            [landlord_email],
            fail_silently=False,
        )
        logger.info(
            "notify_landlord_document_reviewed_task: Sent '%s' notification to landlord "
            "for document %s.",
            new_status,
            document_id,
        )
    except Exception as exc:
        logger.error(
            "notify_landlord_document_reviewed_task: Failed to send landlord notification "
            "for document %s: %s",
            document_id,
            exc,
        )
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Viewing-request notifications
# ---------------------------------------------------------------------------
# Both of these tasks notify the *tenant* in response to a landlord
# action: confirming / declining / completing a request, or proposing
# a new date/time. The in-app notification is created synchronously
# so the bell-icon dropdown updates on the tenant's next request; the
# email is sent in the same task so the notification copy stays in
# one place.

from apps.notifications.models import Notification  # noqa: E402


@shared_task(name="landloards.notify_landlord_viewing_request_status", bind=True, max_retries=3)
def notify_landlord_viewing_request_status_task(self, viewing_request_id, new_status, previous_status=None):
    """
    Notify the tenant when the landlord changes the status of one of
    their viewing requests (confirmed / declined / completed).

    ``new_status`` is a string — one of the values in
    ``ViewingRequest.Status``. ``previous_status`` is only used to
    skip the work if it matches ``new_status`` (defensive guard
    against double-firing).
    """
    from apps.tenant.models import ViewingRequest as _VR
    from apps.home_finder.models import Property

    try:
        viewing_request = (
            _VR.objects
            .select_related("tenant", "property", "property__landlord")
            .get(pk=viewing_request_id)
        )
    except _VR.DoesNotExist:
        logger.warning(
            "notify_landlord_viewing_request_status_task: viewing request %s "
            "no longer exists; skipping.",
            viewing_request_id,
        )
        return

    if previous_status is not None and previous_status == new_status:
        logger.info(
            "notify_landlord_viewing_request_status_task: status unchanged for "
            "viewing request %s; skipping.",
            viewing_request_id,
        )
        return

    tenant = viewing_request.tenant
    tenant_email = viewing_request.requester_email
    tenant_name = viewing_request.requester_name

    if not tenant_email:
        logger.info(
            "notify_landlord_viewing_request_status_task: viewing request %s has "
            "no tenant/email; skipping.",
            viewing_request_id,
        )
        return

    property_title = viewing_request.property.title
    preferred_date = viewing_request.preferred_date
    preferred_time = viewing_request.preferred_time

    if new_status == _VR.Status.CONFIRMED:
        subject = f"Viewing confirmed: {property_title}"
        title = f"Viewing confirmed: {property_title}"
        body_lines = [
            f"Hi {tenant_name},",
            "",
            f"Your viewing request for \"{property_title}\" has been confirmed.",
            f"Date: {preferred_date:%A, %b %-d, %Y if preferred_date else 'TBD'}",
            f"Time: {preferred_time:%-I:%M %p if preferred_time else 'TBD'}",
            "",
            "Please arrive a few minutes early and let the landlord know if you need to reschedule.",
        ]
    elif new_status == _VR.Status.CANCELLED:
        subject = f"Viewing request declined: {property_title}"
        title = f"Viewing declined: {property_title}"
        body_lines = [
            f"Hi {tenant_name},",
            "",
            f"Unfortunately, the landlord couldn't accommodate your viewing "
            f"request for \"{property_title}\".",
            "",
            "Feel free to browse other matching properties or send a new request "
            "when your schedule frees up.",
        ]
    elif new_status == _VR.Status.COMPLETED:
        subject = f"Viewing completed: {property_title}"
        title = f"Viewing completed: {property_title}"
        body_lines = [
            f"Hi {tenant_name},",
            "",
            f"Your viewing for \"{property_title}\" has been marked as completed.",
            "",
            "If you'd like to move forward, you can save the property or contact "
            "the landlord directly from the property page.",
        ]
    else:
        logger.info(
            "notify_landlord_viewing_request_status_task: viewing request %s "
            "transitioned to '%s'; no email sent.",
            viewing_request_id, new_status,
        )
        return

    # 1. In-app notification for registered tenant (sync, so the bell-icon updates immediately).
    if tenant and getattr(tenant, "pk", None):
        try:
            from django.contrib.contenttypes.models import ContentType
            property_ct = ContentType.objects.get_for_model(Property)
            Notification.objects.create(
                user=tenant,
                created_by=None,
                title=title,
                content="\n".join(body_lines),
                content_type=property_ct,
                object_id=str(viewing_request.property_id),
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.error(
                "notify_landlord_viewing_request_status_task: failed to create in-app "
                "notification for viewing request %s: %s",
                viewing_request_id, exc,
            )

    # 2. Email (sent to both registered tenants and guest requesters).
    try:
        send_mail(
            subject=subject,
            message="\n".join(body_lines),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
            recipient_list=[tenant_email],
            fail_silently=False,
        )
        logger.info(
            "notify_landlord_viewing_request_status_task: sent '%s' notification to "
            "requester %s for viewing request %s.",
            new_status, tenant_email, viewing_request_id,
        )
    except Exception as exc:

        logger.error(
            "notify_landlord_viewing_request_status_task: failed to send email for "
            "viewing request %s: %s",
            viewing_request_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="landloards.notify_landlord_viewing_request_rescheduled", bind=True, max_retries=3)
def notify_landlord_viewing_request_rescheduled_task(
    self, viewing_request_id, previous_date="", previous_time="", proposed_by_landlord=False,
):
    """
    Notify the tenant that a viewing request has been rescheduled.

    Works in both directions:
      * ``proposed_by_landlord=True``  → landlord proposed a new time
      * ``proposed_by_landlord=False`` → tenant rescheduled

    The email + in-app notification both explain the change so the
    tenant knows the landlord's calendar (or their own) has moved.
    """
    from apps.tenant.models import ViewingRequest as _VR

    try:
        viewing_request = (
            _VR.objects
            .select_related("tenant", "property", "property__landlord")
            .get(pk=viewing_request_id)
        )
    except _VR.DoesNotExist:
        logger.warning(
            "notify_landlord_viewing_request_rescheduled_task: viewing request %s "
            "no longer exists; skipping.",
            viewing_request_id,
        )
        return

    tenant = viewing_request.tenant
    if not tenant or not getattr(tenant, "email", None):
        logger.info(
            "notify_landlord_viewing_request_rescheduled_task: viewing request %s "
            "has no tenant/email; skipping.",
            viewing_request_id,
        )
        return

    property_title = viewing_request.property.title
    new_date = viewing_request.preferred_date
    new_time = viewing_request.preferred_time

    actor = "the landlord" if proposed_by_landlord else "you"
    counterparty_action = (
        "The landlord has proposed a new time" if proposed_by_landlord
        else "You have proposed a new time"
    )

    subject = f"Viewing rescheduled: {property_title}"
    title = f"Viewing rescheduled: {property_title}"

    body_lines = [
        f"Hi {tenant.full_name},",
        "",
        f"{counterparty_action} for the viewing of \"{property_title}\".",
    ]
    if previous_date or previous_time:
        body_lines.append("")
        body_lines.append("Previous time:")
        body_lines.append(f"  Date: {previous_date or '—'}")
        body_lines.append(f"  Time: {previous_time or '—'}")
    body_lines += [
        "",
        "New time:",
        f"  Date: {new_date:%A, %b %-d, %Y}" if new_date else "  Date: TBD",
        f"  Time: {new_time:%-I:%M %p}" if new_time else "  Time: TBD",
        "",
        (
            "Please confirm the new time from your Viewing Requests page so the "
            "landlord can finalize their schedule."
            if proposed_by_landlord
            else "The landlord has been notified and will confirm the new time shortly."
        ),
    ]

    # 1. In-app notification
    try:
        from django.contrib.contenttypes.models import ContentType
        from apps.home_finder.models import Property
        property_ct = ContentType.objects.get_for_model(Property)
        Notification.objects.create(
            user=tenant,
            created_by=None,
            title=title,
            content="\n".join(body_lines),
            content_type=property_ct,
            object_id=str(viewing_request.property_id),
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.error(
            "notify_landlord_viewing_request_rescheduled_task: failed to create "
            "in-app notification for viewing request %s: %s",
            viewing_request_id, exc,
        )

    # 2. Email
    try:
        send_mail(
            subject=subject,
            message="\n".join(body_lines),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
            recipient_list=[tenant.email],
            fail_silently=False,
        )
        logger.info(
            "notify_landlord_viewing_request_rescheduled_task: sent reschedule "
            "notification to tenant %s for viewing request %s.",
            tenant.email, viewing_request_id,
        )
    except Exception as exc:
        logger.error(
            "notify_landlord_viewing_request_rescheduled_task: failed to send email "
            "for viewing request %s: %s",
            viewing_request_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Landlord-side viewing-request notifications
# ---------------------------------------------------------------------------
# These tasks notify the *landlord* when a tenant does something on a
# viewing request: creates one, or cancels one. (Tenant-side
# notifications in response to landlord actions live in the
# ``notify_landlord_viewing_request_*_task`` functions above.)
#
# Both tasks create an in-app Notification entry tied to the
# ViewingRequest's Property as the generic target, so the bell-icon
# dropdown updates on the landlord's next request and the link in the
# notification can deep-link back to the inbox / detail page.


@shared_task(
    name="landloards.notify_landlord_viewing_request_created",
    bind=True,
    max_retries=3,
)
def notify_landlord_viewing_request_created_task(self, viewing_request_id):
    """
    Notify the landlord that a tenant just created a new viewing
    request on one of their properties. The landlord's dashboard /
    sidebar badge will pick this up on the next page load via the
    invalidated cached count.
    """
    from apps.tenant.models import ViewingRequest as _VR

    try:
        viewing_request = (
            _VR.objects
            .select_related("tenant", "property", "property__landlord")
            .get(pk=viewing_request_id)
        )
    except _VR.DoesNotExist:
        logger.warning(
            "notify_landlord_viewing_request_created_task: viewing request %s "
            "no longer exists; skipping.",
            viewing_request_id,
        )
        return

    landlord = getattr(viewing_request.property, "landlord", None)
    landlord_email = getattr(landlord, "email", None) if landlord else None
    if not landlord_email:
        logger.info(
            "notify_landlord_viewing_request_created_task: viewing request %s "
            "has no landlord/email; skipping.",
            viewing_request_id,
        )
        return

    property_title = viewing_request.property.title
    tenant = viewing_request.tenant
    requester_name = viewing_request.requester_name
    requester_email = viewing_request.requester_email
    requester_phone = viewing_request.requester_phone
    guest_badge = " (Guest)" if viewing_request.is_guest else ""

    preferred_date = viewing_request.preferred_date
    preferred_time = viewing_request.preferred_time

    subject = f"New viewing request: {property_title}"
    title = f"New viewing request: {property_title}"

    body_lines = [
        f"Hi {landlord.full_name},",
        "",
        f"{requester_name}{guest_badge} has just requested a viewing tour of your property \"{property_title}\".",
        "",
        "Requester Details:",
        f"  Name: {requester_name}",
    ]
    if requester_email:
        body_lines.append(f"  Email: {requester_email}")
    if requester_phone:
        body_lines.append(f"  Phone: {requester_phone}")

    body_lines += [
        "",
        "Requested Time:",
        f"  Date: {preferred_date:%A, %b %-d, %Y}" if preferred_date else "  Date: TBD",
        f"  Time: {preferred_time:%-I:%M %p}" if preferred_time else "  Time: TBD",
    ]
    if viewing_request.notes:
        body_lines += [
            "",
            "Requester Notes:",
            f"  {viewing_request.notes}",
        ]
    body_lines += [
        "",
        "Open the Viewing Requests page in your dashboard to confirm, "
        "decline, or contact the requester directly.",
    ]


    # 1. In-app notification (sync, so the bell-icon updates immediately).
    try:
        from django.contrib.contenttypes.models import ContentType
        from apps.home_finder.models import Property
        property_ct = ContentType.objects.get_for_model(Property)
        Notification.objects.create(
            user=landlord,
            created_by=tenant if getattr(tenant, "pk", None) else None,
            title=title,
            content="\n".join(body_lines),
            content_type=property_ct,
            object_id=str(viewing_request.property_id),
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.error(
            "notify_landlord_viewing_request_created_task: failed to create in-app "
            "notification for viewing request %s: %s",
            viewing_request_id, exc,
        )

    # 2. Email.
    try:
        send_mail(
            subject=subject,
            message="\n".join(body_lines),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
            recipient_list=[landlord_email],
            fail_silently=False,
        )
        logger.info(
            "notify_landlord_viewing_request_created_task: sent 'created' "
            "notification to landlord %s for viewing request %s.",
            landlord_email, viewing_request_id,
        )
    except Exception as exc:
        logger.error(
            "notify_landlord_viewing_request_created_task: failed to send email "
            "for viewing request %s: %s",
            viewing_request_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)


@shared_task(
    name="landloards.notify_landlord_viewing_request_cancelled",
    bind=True,
    max_retries=3,
)
def notify_landlord_viewing_request_cancelled_task(self, viewing_request_id, previous_status=None):
    """
    Notify the landlord that a tenant cancelled one of their viewing
    requests. ``previous_status`` is informational (pending vs confirmed)
    so the email can explain whether the landlord's slot just freed up
    from a confirmed appointment, or whether it was only a tentative
    request that never got confirmed.
    """
    from apps.tenant.models import ViewingRequest as _VR

    try:
        viewing_request = (
            _VR.objects
            .select_related("tenant", "property", "property__landlord")
            .get(pk=viewing_request_id)
        )
    except _VR.DoesNotExist:
        logger.warning(
            "notify_landlord_viewing_request_cancelled_task: viewing request %s "
            "no longer exists; skipping.",
            viewing_request_id,
        )
        return

    # Defensive: skip if the status didn't actually move to cancelled.
    # (We compare against the value passed by the caller — by the time
    # this task runs, the row has already been saved as CANCELLED, so
    # checking ``viewing_request.status`` here would always be True.)
    if previous_status is not None and previous_status == _VR.Status.CANCELLED:
        logger.info(
            "notify_landlord_viewing_request_cancelled_task: viewing request %s "
            "was already cancelled; skipping.",
            viewing_request_id,
        )
        return

    landlord = getattr(viewing_request.property, "landlord", None)
    landlord_email = getattr(landlord, "email", None) if landlord else None
    if not landlord_email:
        logger.info(
            "notify_landlord_viewing_request_cancelled_task: viewing request %s "
            "has no landlord/email; skipping.",
            viewing_request_id,
        )
        return

    property_title = viewing_request.property.title
    tenant = viewing_request.tenant
    tenant_name = getattr(tenant, "full_name", "") or tenant.email
    preferred_date = viewing_request.preferred_date
    preferred_time = viewing_request.preferred_time

    subject = f"Viewing request cancelled: {property_title}"
    title = f"Viewing request cancelled: {property_title}"

    was_confirmed = previous_status == _VR.Status.CONFIRMED
    slot_block = (
        "Your confirmed slot is now free, so you may want to re-open "
        "your calendar for that time."
        if was_confirmed
        else "Since this was a pending request, nothing on your calendar "
             "needs to change."
    )

    body_lines = [
        f"Hi {landlord.full_name},",
        "",
        f"{tenant_name} has cancelled their viewing request for "
        f"\"{property_title}\".",
        "",
        "Requested time:",
        f"  Date: {preferred_date:%A, %b %-d, %Y}" if preferred_date else "  Date: TBD",
        f"  Time: {preferred_time:%-I:%M %p}" if preferred_time else "  Time: TBD",
        "",
        slot_block,
    ]

    # 1. In-app notification.
    try:
        from django.contrib.contenttypes.models import ContentType
        from apps.home_finder.models import Property
        property_ct = ContentType.objects.get_for_model(Property)
        Notification.objects.create(
            user=landlord,
            created_by=tenant if getattr(tenant, "pk", None) else None,
            title=title,
            content="\n".join(body_lines),
            content_type=property_ct,
            object_id=str(viewing_request.property_id),
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.error(
            "notify_landlord_viewing_request_cancelled_task: failed to create in-app "
            "notification for viewing request %s: %s",
            viewing_request_id, exc,
        )

    # 2. Email.
    try:
        send_mail(
            subject=subject,
            message="\n".join(body_lines),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
            recipient_list=[landlord_email],
            fail_silently=False,
        )
        logger.info(
            "notify_landlord_viewing_request_cancelled_task: sent 'cancelled' "
            "notification to landlord %s for viewing request %s.",
            landlord_email, viewing_request_id,
        )
    except Exception as exc:
        logger.error(
            "notify_landlord_viewing_request_cancelled_task: failed to send email "
            "for viewing request %s: %s",
            viewing_request_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)

