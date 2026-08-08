import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


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