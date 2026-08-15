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

    if new_status == Property.VerificationStatus.VERIFIED:
        subject = f"Your property has been verified: {property_obj.title}"
        message = (
            f"Hi {landlord.full_name},\n\n"
            f"Great news! Your property has been reviewed and verified by our team.\n\n"
            f"Details:\n"
            f"  - Title: {property_obj.title}\n"
            f"  - Reference: {property_obj.reference_number}\n"
            f"  - Verification status: {status_display}\n\n"
            f"Your listing is now eligible to be published and shown to tenants.\n\n"
            f"Thank you for using Vacant Hommie!"
        )
    elif new_status == Property.VerificationStatus.REJECTED:
        subject = f"Your property verification was rejected: {property_obj.title}"
        message = (
            f"Hi {landlord.full_name},\n\n"
            f"Unfortunately, your property submission could not be verified.\n\n"
            f"Details:\n"
            f"  - Title: {property_obj.title}\n"
            f"  - Reference: {property_obj.reference_number}\n"
            f"  - Verification status: {status_display}\n\n"
            f"Please review the listing, make any necessary corrections, and resubmit.\n"
            f"If you believe this was a mistake, contact our support team.\n\n"
            f"Vacant Hommie"
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
    Background task that emails the landlord when one of their uploaded
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
        else "Not linked to a specific property"
    )

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
            f"Vacant Hommie"
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
            f"Vacant Hommie"
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
