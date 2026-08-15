import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives, send_mail
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Trial reminder configuration
# ---------------------------------------------------------------------------
# How many days BEFORE the trial ends we email the landlord. A single
# 3-day reminder is the default; the tuple lets ops adjust without
# changing the task code (e.g. (7, 3, 1) for a 7/3/1 reminder cadence).
# The list is intentionally small — every reminder is an email we send,
# and we don't want to spam landlords during a 30-day window.
TRIAL_REMINDER_DAYS_AHEAD = (3, 1)


# ---------------------------------------------------------------------------
# Shared email helper
# ---------------------------------------------------------------------------

def _send_email(subject, template_name, context, to_email):
    html_body = render_to_string(template_name, context)
    text_body = strip_tags(html_body)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=False)


# Shared decorator options for every email task in this file
_TASK_KWARGS = dict(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)


# ---------------------------------------------------------------------------
# Payment confirmation (new subscription or upgrade)
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_subscription_confirmation_email(self, subscription_id):
    from .models import LandlordSubscription

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=subscription_id)
    except LandlordSubscription.DoesNotExist:
        logger.warning(
            "send_subscription_confirmation_email: subscription %s no longer exists",
            subscription_id,
        )
        return

    landlord = subscription.landlord
    plan = subscription.plan

    _send_email(
        subject=f"Your {plan.name} subscription is active",
        template_name='subscription/emails/subscription_confirmed.html',
        context={
            'full_name': landlord.full_name,
            'plan_name': plan.name,
            'price': plan.price,
            'start_date': subscription.start_date,
            'end_date': subscription.end_date,
            'maximum_listings': plan.maximum_listings,
        },
        to_email=landlord.email,
    )
    logger.info(
        "Subscription confirmation email sent to %s for subscription %s",
        landlord.email, subscription_id,
    )


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_cancellation_email(self, subscription_id, immediate=False):
    from .models import LandlordSubscription

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=subscription_id)
    except LandlordSubscription.DoesNotExist:
        logger.warning(
            "send_cancellation_email: subscription %s no longer exists",
            subscription_id,
        )
        return

    landlord = subscription.landlord
    plan = subscription.plan

    _send_email(
        subject=f"Your {plan.name} subscription has been cancelled",
        template_name='subscription/emails/subscription_cancelled.html',
        context={
            'full_name': landlord.full_name,
            'plan_name': plan.name,
            'end_date': subscription.end_date,
            'immediate': immediate,
        },
        to_email=landlord.email,
    )
    logger.info(
        "Cancellation email sent to %s for subscription %s (immediate=%s)",
        landlord.email, subscription_id, immediate,
    )


# ---------------------------------------------------------------------------
# Reactivation
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_reactivation_email(self, subscription_id):
    from .models import LandlordSubscription

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=subscription_id)
    except LandlordSubscription.DoesNotExist:
        logger.warning(
            "send_reactivation_email: subscription %s no longer exists",
            subscription_id,
        )
        return

    landlord = subscription.landlord
    plan = subscription.plan

    _send_email(
        subject=f"Your {plan.name} subscription has been reactivated",
        template_name='subscription/emails/subscription_reactivated.html',
        context={
            'full_name': landlord.full_name,
            'plan_name': plan.name,
            'end_date': subscription.end_date,
        },
        to_email=landlord.email,
    )
    logger.info(
        "Reactivation email sent to %s for subscription %s",
        landlord.email, subscription_id,
    )


# ---------------------------------------------------------------------------
# Downgrade scheduled (immediate confirmation that it's queued)
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_downgrade_scheduled_email(self, subscription_id, new_plan_id):
    from .models import LandlordSubscription, SubscriptionPlan

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=subscription_id)
        new_plan = SubscriptionPlan.objects.get(id=new_plan_id)
    except (LandlordSubscription.DoesNotExist, SubscriptionPlan.DoesNotExist):
        logger.warning(
            "send_downgrade_scheduled_email: subscription %s or plan %s no longer exists",
            subscription_id, new_plan_id,
        )
        return

    landlord = subscription.landlord

    _send_email(
        subject=f"Your plan will change to {new_plan.name}",
        template_name='subscription/emails/downgrade_scheduled.html',
        context={
            'full_name': landlord.full_name,
            'current_plan_name': subscription.plan.name,
            'new_plan_name': new_plan.name,
            'effective_date': subscription.end_date,
        },
        to_email=landlord.email,
    )
    logger.info(
        "Downgrade-scheduled email sent to %s for subscription %s → plan %s",
        landlord.email, subscription_id, new_plan_id,
    )


# ---------------------------------------------------------------------------
# Downgrade applied / subscription expired (fired by the daily task below)
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_downgrade_applied_email(self, new_subscription_id):
    from .models import LandlordSubscription

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=new_subscription_id)
    except LandlordSubscription.DoesNotExist:
        logger.warning(
            "send_downgrade_applied_email: subscription %s no longer exists",
            new_subscription_id,
        )
        return

    landlord = subscription.landlord
    plan = subscription.plan

    _send_email(
        subject=f"You're now on the {plan.name} plan",
        template_name='subscription/emails/downgrade_applied.html',
        context={
            'full_name': landlord.full_name,
            'plan_name': plan.name,
            'maximum_listings': plan.maximum_listings,
            'end_date': subscription.end_date,
        },
        to_email=landlord.email,
    )
    logger.info(
        "Downgrade-applied email sent to %s for new subscription %s",
        landlord.email, new_subscription_id,
    )


@shared_task(**_TASK_KWARGS)
def send_subscription_expired_email(self, landlord_id, plan_name):
    from apps.account.models import User

    try:
        landlord = User.objects.get(id=landlord_id)
    except User.DoesNotExist:
        logger.warning("send_subscription_expired_email: user %s no longer exists", landlord_id)
        return

    _send_email(
        subject="Your subscription has expired",
        template_name='subscription/emails/subscription_expired.html',
        context={
            'full_name': landlord.full_name,
            'plan_name': plan_name,
        },
        to_email=landlord.email,
    )
    logger.info("Expiry email sent to %s", landlord.email)


# ---------------------------------------------------------------------------
# Daily scheduled task — applies downgrades, expires lapsed subscriptions
# ---------------------------------------------------------------------------

@shared_task
def expire_and_apply_scheduled_changes():
    """
    Runs daily (see CELERY_BEAT_SCHEDULE). For every subscription whose
    period has ended:
      - marks it inactive
      - if a downgrade was scheduled (pending_plan set, not cancelled),
        activates the new plan and notifies the landlord
      - otherwise, if it wasn't renewed, notifies the landlord it expired
    """
    from .models import LandlordSubscription

    now = timezone.now()
    expiring = LandlordSubscription.objects.filter(
        status=LandlordSubscription.Status.SUCCESS,
        is_active=True,
        end_date__lte=now,
    ).select_related('landlord', 'plan')

    processed = 0
    for sub in expiring:
        with transaction.atomic():
            locked = LandlordSubscription.objects.select_for_update().get(pk=sub.pk)

            # Guard against a race: another worker may have already processed this row
            if not locked.is_active or locked.end_date > timezone.now():
                continue

            locked.is_active = False
            locked.save(update_fields=['is_active'])

            if locked.pending_plan_id and not locked.cancel_at_period_end:
                new_sub = LandlordSubscription.objects.create(
                    landlord=locked.landlord,
                    plan=locked.pending_plan,
                    status=LandlordSubscription.Status.SUCCESS,
                )
                new_sub.activate()
                transaction.on_commit(
                    lambda ns=new_sub: send_downgrade_applied_email.delay(ns.id)
                )
            else:
                transaction.on_commit(
                    lambda landlord_id=locked.landlord_id, plan_name=locked.plan.name:
                        send_subscription_expired_email.delay(landlord_id, plan_name)
                )

            processed += 1

    logger.info("expire_and_apply_scheduled_changes processed %s subscription(s)", processed)
    return processed


# ---------------------------------------------------------------------------
# Daily beat task: expire landlord free trials
# ---------------------------------------------------------------------------

@shared_task
def expire_landlord_free_trials():
    """
    Runs daily (CELERY_BEAT_SCHEDULE). For every landlord whose trial
    has ended, who does NOT currently have an active paid subscription,
    AND who hasn't already been notified, send a one-time
    "your trial has ended" email.

    The one-time guarantee is provided by the
    ``User.notified_trial_ended_at`` timestamp: the WHERE clause
    requires it to be NULL, and we set it on the same row inside
    the same transaction that scheduled the email. Re-running the
    task the next day sees NULL-set rows and skips them, so a
    landlord who never subscribes receives the email exactly once
    instead of every day.

    We don't "clear" ``trial_start_date`` / ``trial_end_date`` —
    leaving them set is intentional so the dashboard and guard can
    still tell the user "your trial ended on X" instead of "you
    never had a trial".
    """
    admin_role = getattr(User.Role, "LANDLORD", "landlord")
    now = timezone.now()

    # Landlords whose trial has ended AND who we haven't notified yet.
    # Filtering on ``notified_trial_ended_at IS NULL`` is what makes
    # this one-time per landlord.
    candidates = User.objects.filter(
        role=admin_role,
        trial_end_date__lte=now,
        notified_trial_ended_at__isnull=True,
    )

    processed = 0
    for landlord in candidates:
        # Skip if the landlord now has an active paid subscription —
        # the subscription confirmation email already covered the
        # transition, and we don't want to also send "your trial
        # ended" after they've converted.
        from .models import LandlordSubscription
        has_active_sub = LandlordSubscription.objects.filter(
            landlord=landlord,
            status=LandlordSubscription.Status.SUCCESS,
            is_active=True,
            end_date__gt=now,
        ).exists()
        if has_active_sub:
            # Mark as notified anyway so we don't re-evaluate this
            # landlord every day.
            User.objects.filter(pk=landlord.pk).update(
                notified_trial_ended_at=now,
            )
            continue

        # Mark notified *before* dispatching, so a Celery retry (or a
        # second beat run that overlaps this one) doesn't double-email.
        # The email itself is queued via on_commit so we don't dispatch
        # if the surrounding transaction rolls back.
        with transaction.atomic():
            updated = User.objects.filter(
                pk=landlord.pk,
                notified_trial_ended_at__isnull=True,
            ).update(notified_trial_ended_at=now)
            if updated == 0:
                # Lost the race to a concurrent worker.
                continue
            transaction.on_commit(
                lambda lid=landlord.id, name=landlord.full_name:
                    send_trial_ended_email_task.delay(lid, name)
            )
        processed += 1

    logger.info("expire_landlord_free_trials: notified %s landlord(s)", processed)
    return processed


@shared_task(**_TASK_KWARGS)
def send_trial_ended_email_task(self, landlord_id, full_name):
    """
    "Your free trial has ended" email. Kept as its own task so the daily
    expiry job stays fast and any email-server hiccup is auto-retried by
    Celery without re-querying the DB.
    """
    _send_email(
        subject="Your free trial has ended",
        template_name='subscription/emails/trial_ended.html',
        context={'full_name': full_name},
        to_email=User.objects.get(id=landlord_id).email,
    )
    logger.info("Trial-ended email sent to landlord %s", landlord_id)


# ---------------------------------------------------------------------------
# Daily beat task: queue trial-ending reminders
# ---------------------------------------------------------------------------

@shared_task
def send_trial_ending_reminders():
    """
    Runs daily (CELERY_BEAT_SCHEDULE). For every landlord whose trial
    ends in exactly N days (where N is in ``TRIAL_REMINDER_DAYS_AHEAD``)
    AND who does not already have an active paid subscription, queue a
    reminder email.

    Idempotency is provided by the date check itself: we only queue a
    reminder when ``trial_end_date`` falls on the target day. Re-running
    the task on the same day won't double-email because the date match
    is exact, and the task itself is a no-op on non-target days.

    We skip landlords who already have a paid subscription — they're
    converting anyway, no need to nudge them about a trial.
    """
    from .models import LandlordSubscription

    today = timezone.now().date()
    total_queued = 0

    for days_ahead in TRIAL_REMINDER_DAYS_AHEAD:
        target_day = today + timezone.timedelta(days=days_ahead)
        # trial_end_date is a datetime; compare the date portion.
        candidate_ids = list(
            User.objects.filter(
                role=User.Role.LANDLORD,
                trial_started=True,
                trial_end_date__date=target_day,
            ).values_list("id", flat=True)
        )

        for landlord_id in candidate_ids:
            # Skip if the landlord has since subscribed — the subscription
            # confirmation email already covered the transition.
            has_active_sub = LandlordSubscription.objects.filter(
                landlord_id=landlord_id,
                status=LandlordSubscription.Status.SUCCESS,
                is_active=True,
                end_date__gt=timezone.now(),
            ).exists()
            if has_active_sub:
                continue

            transaction.on_commit(
                lambda lid=landlord_id, d=days_ahead:
                    send_trial_ending_reminder_email_task.delay(lid, d)
            )
            total_queued += 1

    logger.info(
        "send_trial_ending_reminders: queued %s reminder(s) for %s.",
        total_queued, today,
    )
    return total_queued


@shared_task(**_TASK_KWARGS)
def send_trial_ending_reminder_email_task(self, landlord_id, days_remaining):
    """
    "Your free trial ends in N day(s)" email — the conversion moment.
    Sent by ``send_trial_ending_reminders`` for every landlord whose
    trial ends in N days. Single-task-per-email so the daily beat job
    stays fast and any email-server hiccup is auto-retried by Celery.
    """
    try:
        landlord = User.objects.get(id=landlord_id)
    except User.DoesNotExist:
        logger.warning(
            "send_trial_ending_reminder_email_task: landlord %s no longer exists",
            landlord_id,
        )
        return

    if not landlord.email:
        return

    # Defensive: if the trial already ended between scheduling and
    # execution (rare but possible — a beat delay of >1 day, or a
    # manual reset), skip the email so we don't tell them to act on a
    # trial that's already over.
    from django.utils import timezone
    if not landlord.trial_started or landlord.trial_end_date <= timezone.now():
        logger.info(
            "send_trial_ending_reminder_email_task: trial for landlord %s no longer "
            "active; skipping reminder.",
            landlord_id,
        )
        return

    _send_email(
        subject=f"Your free trial ends in {days_remaining} day(s)",
        template_name='subscription/emails/trial_ending_reminder.html',
        context={
            'full_name': landlord.full_name,
            'days_remaining': days_remaining,
            'trial_end_date': landlord.trial_end_date,
        },
        to_email=landlord.email,
    )
    logger.info(
        "Trial-ending reminder sent to landlord %s (%s day(s) remaining)",
        landlord_id, days_remaining,
    )


# ---------------------------------------------------------------------------
# Admin-recipient helper (used by the admin-notification tasks below)
# ---------------------------------------------------------------------------

def _admin_recipient_q():
    """
    Q object matching admin users: superusers, staff, or role='admin'.
    Mirrors the helper in apps/landloards/tasks.py so the two apps apply
    the same "who counts as an admin" policy.
    """
    admin_role = getattr(User.Role, "ADMIN", "admin")
    return Q(is_superuser=True) | Q(is_staff=True) | Q(role=admin_role)


def _admin_emails():
    """Return a de-duplicated list of active admin/superuser email addresses."""
    emails = list(
        User.objects.filter(is_active=True)
        .filter(_admin_recipient_q())
        .values_list("email", flat=True)
    )
    return [e for e in dict.fromkeys(emails) if e]


# ---------------------------------------------------------------------------
# Admin notification: new paying subscription
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_admin_new_subscription_notification_task(self, subscription_id):
    """
    Notify all admins/superusers that a landlord just successfully
    activated a subscription. Fires after _confirm_subscription().
    """
    from .models import LandlordSubscription

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=subscription_id)
    except LandlordSubscription.DoesNotExist:
        logger.warning(
            "send_admin_new_subscription_notification_task: subscription %s missing",
            subscription_id,
        )
        return

    admin_emails = _admin_emails()
    if not admin_emails:
        logger.info(
            "send_admin_new_subscription_notification_task: no admin emails; skipping."
        )
        return

    landlord = subscription.landlord
    plan = subscription.plan

    subject = f"[New Subscription] {landlord.full_name} subscribed to {plan.name}"
    message = (
        f"Hello Admin,\n\n"
        f"A landlord has just successfully subscribed to a plan.\n\n"
        f"Details:\n"
        f"  - Landlord: {landlord.full_name}\n"
        f"  - Email: {landlord.email}\n"
        f"  - Phone: {landlord.phone_number}\n"
        f"  - Plan: {plan.name}\n"
        f"  - Price: {plan.price} ({plan.duration_days} days)\n"
        f"  - Max listings: {plan.maximum_listings}\n"
        f"  - Start date: {subscription.start_date:%Y-%m-%d %H:%M}\n"
        f"  - End date: {subscription.end_date:%Y-%m-%d %H:%M}\n"
        f"  - Payment reference: {subscription.payment_reference or 'N/A'}\n\n"
        f"Admin link: /admin/Subscription/landlordsubscription/{subscription.id}/change/\n\n"
        f"Vacant Hommie"
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
            "send_admin_new_subscription_notification_task: notified %d admin(s) "
            "about subscription %s.",
            len(admin_emails), subscription_id,
        )
    except Exception as exc:
        logger.error(
            "send_admin_new_subscription_notification_task: failed for %s: %s",
            subscription_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Landlord notification: payment failed
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_payment_failed_email_task(self, subscription_id, reason="Payment was not successful."):
    """
    Email the landlord when a payment attempt fails so they can retry
    (different card, retry button, etc.).
    """
    from .models import LandlordSubscription

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=subscription_id)
    except LandlordSubscription.DoesNotExist:
        logger.warning(
            "send_payment_failed_email_task: subscription %s missing", subscription_id
        )
        return

    landlord = subscription.landlord
    if not landlord.email:
        return

    subject = f"Payment failed for your {subscription.plan.name} subscription"
    message = (
        f"Hi {landlord.full_name},\n\n"
        f"We were unable to process your recent payment for the "
        f"{subscription.plan.name} plan.\n\n"
        f"Reason: {reason}\n\n"
        f"Please update your payment method or try again so your "
        f"subscription stays active and your listings remain visible.\n\n"
        f"Reference: {subscription.payment_reference or 'N/A'}\n\n"
        f"Vacant Hommie"
    )

    try:
        send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
            [landlord.email],
            fail_silently=False,
        )
        logger.info(
            "send_payment_failed_email_task: notified landlord for subscription %s.",
            subscription_id,
        )
    except Exception as exc:
        logger.error(
            "send_payment_failed_email_task: failed for %s: %s", subscription_id, exc
        )
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Admin notification: payment failed
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_admin_payment_failed_notification_task(self, subscription_id, reason=""):
    """
    Notify all admins when a payment fails — useful for spotting provider
    outages, fraud, or accounts that need manual follow-up.
    """
    from .models import LandlordSubscription

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=subscription_id)
    except LandlordSubscription.DoesNotExist:
        logger.warning(
            "send_admin_payment_failed_notification_task: subscription %s missing",
            subscription_id,
        )
        return

    admin_emails = _admin_emails()
    if not admin_emails:
        return

    landlord = subscription.landlord
    subject = f"[Payment Failed] {landlord.full_name} — {subscription.plan.name}"
    message = (
        f"Hello Admin,\n\n"
        f"A subscription payment has failed.\n\n"
        f"Details:\n"
        f"  - Landlord: {landlord.full_name} ({landlord.email})\n"
        f"  - Plan: {subscription.plan.name}\n"
        f"  - Reference: {subscription.payment_reference or 'N/A'}\n"
        f"  - Reason: {reason or 'Not specified'}\n\n"
        f"Admin link: /admin/Subscription/landlordsubscription/{subscription.id}/change/\n\n"
        f"Vacant Hommie"
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
            "send_admin_payment_failed_notification_task: notified %d admin(s) "
            "about failed payment for subscription %s.",
            len(admin_emails), subscription_id,
        )
    except Exception as exc:
        logger.error(
            "send_admin_payment_failed_notification_task: failed for %s: %s",
            subscription_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Admin notification: cancellation
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_admin_subscription_cancelled_notification_task(
    self, subscription_id, immediate=False
):
    """
    Notify all admins that a landlord cancelled their subscription. Useful
    for churn dashboards and for the support team to follow up.
    """
    from .models import LandlordSubscription

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=subscription_id)
    except LandlordSubscription.DoesNotExist:
        logger.warning(
            "send_admin_subscription_cancelled_notification_task: subscription %s missing",
            subscription_id,
        )
        return

    admin_emails = _admin_emails()
    if not admin_emails:
        return

    landlord = subscription.landlord
    when = "immediately" if immediate else (
        f"on {subscription.end_date:%Y-%m-%d %H:%M}" if subscription.end_date
        else "at the end of the billing period"
    )
    subject = f"[Cancellation] {landlord.full_name} cancelled {subscription.plan.name}"
    message = (
        f"Hello Admin,\n\n"
        f"A landlord has cancelled their subscription.\n\n"
        f"Details:\n"
        f"  - Landlord: {landlord.full_name} ({landlord.email})\n"
        f"  - Plan: {subscription.plan.name}\n"
        f"  - Effective: {when}\n"
        f"  - Reference: {subscription.payment_reference or 'N/A'}\n\n"
        f"Admin link: /admin/Subscription/landlordsubscription/{subscription.id}/change/\n\n"
        f"Vacant Hommie"
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
            "send_admin_subscription_cancelled_notification_task: notified %d admin(s) "
            "about cancellation of subscription %s.",
            len(admin_emails), subscription_id,
        )
    except Exception as exc:
        logger.error(
            "send_admin_subscription_cancelled_notification_task: failed for %s: %s",
            subscription_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Landlord notification: renewal reminder (sent N days before end_date)
# ---------------------------------------------------------------------------

@shared_task(**_TASK_KWARGS)
def send_subscription_renewal_reminder_email_task(self, subscription_id, days_remaining):
    """
    Email the landlord a set number of days before their subscription ends
    to remind them to renew. Intended to be called by the daily beat task
    below — ``days_remaining`` is passed in so a single beat entry can send
    a "3 days left" reminder on day N-3 and a "1 day left" reminder on N-1.
    """
    from .models import LandlordSubscription

    try:
        subscription = LandlordSubscription.objects.select_related(
            'landlord', 'plan'
        ).get(id=subscription_id)
    except LandlordSubscription.DoesNotExist:
        logger.warning(
            "send_subscription_renewal_reminder_email_task: subscription %s missing",
            subscription_id,
        )
        return

    landlord = subscription.landlord
    if not landlord.email:
        return

    # If the landlord already cancelled or the sub expired between scheduling
    # and execution, don't send a "renew now" email.
    if subscription.status != LandlordSubscription.Status.SUCCESS or not subscription.is_active:
        logger.info(
            "send_subscription_renewal_reminder_email_task: subscription %s no longer "
            "active; skipping reminder.",
            subscription_id,
        )
        return
    if subscription.cancel_at_period_end:
        logger.info(
            "send_subscription_renewal_reminder_email_task: subscription %s already "
            "set to cancel at period end; skipping reminder.",
            subscription_id,
        )
        return

    plan = subscription.plan
    subject = f"Your {plan.name} subscription expires in {days_remaining} day(s)"
    message = (
        f"Hi {landlord.full_name},\n\n"
        f"This is a friendly reminder that your {plan.name} subscription "
        f"will expire in {days_remaining} day(s) on "
        f"{subscription.end_date:%B %d, %Y}.\n\n"
        f"Renewing on time keeps your listings visible to tenants and "
        f"preserves your {plan.maximum_listings} active listing slots.\n\n"
        f"Thank you for using Vacant Hommie!"
    )

    try:
        send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@homefinder.com"),
            [landlord.email],
            fail_silently=False,
        )
        logger.info(
            "send_subscription_renewal_reminder_email_task: sent %s-day reminder for "
            "subscription %s.",
            days_remaining, subscription_id,
        )
    except Exception as exc:
        logger.error(
            "send_subscription_renewal_reminder_email_task: failed for %s: %s",
            subscription_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Daily beat task: queue renewal reminders
# ---------------------------------------------------------------------------

# How many days before end_date we email the landlord.
# A single reminder 3 days out is a good default; add more entries if you
# want an additional nudge (e.g. 7 days out) — the loop below handles any
# number of values.
RENEWAL_REMINDER_DAYS_AHEAD = (3, 1)


@shared_task
def send_subscription_renewal_reminders():
    """
    Runs daily (CELERY_BEAT_SCHEDULE). For every active subscription that
    has a pending_plan or a cancel_at_period_end flag, do nothing — those
    landlords are intentionally not renewing. For everyone else, queue a
    renewal-reminder email for each day in RENEWAL_REMINDER_DAYS_AHEAD
    that lands exactly N days before end_date today.
    """
    from .models import LandlordSubscription

    today = timezone.now().date()
    total_queued = 0

    for days_ahead in RENEWAL_REMINDER_DAYS_AHEAD:
        target_day = today + timezone.timedelta(days=days_ahead)
        # end_date is a datetime; compare the date portion.
        subs = LandlordSubscription.objects.filter(
            status=LandlordSubscription.Status.SUCCESS,
            is_active=True,
            cancel_at_period_end=False,
            end_date__date=target_day,
        ).values_list("id", flat=True)

        for sub_id in subs:
            transaction.on_commit(
                lambda sid=sub_id, d=days_ahead:
                    send_subscription_renewal_reminder_email_task.delay(sid, d)
            )
            total_queued += 1

    logger.info(
        "send_subscription_renewal_reminders: queued %s reminder(s) for %s.",
        total_queued, today,
    )
    return total_queued