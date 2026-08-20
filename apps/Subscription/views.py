import hashlib
import hmac
import json
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.account.models import User
from .models import LandlordSubscription, SubscriptionPlan
from .services import Paystack, PaystackError, change_subscription_plan
from .tasks import (
    send_admin_new_subscription_notification_task,
    send_admin_payment_failed_notification_task,
    send_admin_subscription_cancelled_notification_task,
    send_cancellation_email,
    send_downgrade_scheduled_email,
    send_payment_failed_email_task,
    send_reactivation_email,
    send_subscription_confirmation_email,
)

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24  # 24 Hours (Plans change rarely)
PLANS_CACHE_KEY = "active_subscription_plans_cache"


# ---------------------------------------------------------------------------
# Views: Plans & Dashboard
# ---------------------------------------------------------------------------
def list_all_subscription(request):
    """Displays available pricing plans with caching enabled."""
    plans = cache.get(PLANS_CACHE_KEY)

    if plans is None:
        plans = list(SubscriptionPlan.objects.filter(is_active=True))
        cache.set(PLANS_CACHE_KEY, plans, CACHE_TTL)

    return render(request, 'Subscription/pricing_plans.html', {'plans': plans})


@login_required
def landlord_subscription_list(request):
    """Landlord billing history and active subscription management view."""
    if request.user.role != User.Role.LANDLORD:
        messages.error(request, "Access restricted to landlords.")
        return redirect('dashboard')

    active_subscription = LandlordSubscription.objects.filter(
        landlord=request.user,
        status=LandlordSubscription.Status.SUCCESS,
        is_active=True
    ).order_by('-end_date').first()

    subscriptions = LandlordSubscription.objects.filter(
        landlord=request.user
    ).select_related('plan').order_by('-created_at')

    context = {
        'active_subscription': active_subscription,
        'subscriptions': subscriptions,
    }
    return render(request, 'landlord_subscription_list.html', context)


# ---------------------------------------------------------------------------
# Views: Payment Initialization & Verification
# ---------------------------------------------------------------------------
@login_required
def initiate_subscription_payment(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)

    active_subscription = (
        LandlordSubscription.objects
        .filter(
            landlord=request.user,
            status=LandlordSubscription.Status.SUCCESS,
            is_active=True,
        )
        .order_by('-end_date')
        .first()
    )

    if active_subscription and active_subscription.is_currently_active:
        if active_subscription.plan_id == plan.id:
            messages.info(
                request,
                f"You already have an active {plan.name} subscription "
                f"running until {active_subscription.end_date:%B %d, %Y}."
            )
            return redirect('landloards:list_landlord_subscription')

        return redirect('landloards:confirm_plan_change', plan_id=plan.id)

    reference = f"sub_{request.user.id}_{uuid.uuid4().hex[:12]}"

    subscription = LandlordSubscription.objects.create(
        landlord=request.user,
        plan=plan,
        payment_reference=reference,
        status=LandlordSubscription.Status.PENDING,
    )

    callback_url = request.build_absolute_uri(reverse('subscription:paystack_callback'))

    paystack = Paystack(data={
        'email': request.user.email,
        'amount': int(plan.price * 100),
        'reference': reference,
        'callback_url': callback_url,
        'metadata': {'subscription_id': str(subscription.id), 'plan_id': str(plan.id)},
    })

    try:
        result = paystack.initiate_payment()
    except PaystackError as e:
        subscription.status = LandlordSubscription.Status.FAILED
        subscription.save(update_fields=['status'])
        # Notify the landlord (and admins) that the payment couldn't start
        transaction.on_commit(
            lambda sid=subscription.id, msg=str(e):
                send_payment_failed_email_task.delay(sid, reason=msg)
        )
        transaction.on_commit(
            lambda sid=subscription.id, msg=str(e):
                send_admin_payment_failed_notification_task.delay(sid, reason=msg)
        )
        messages.error(request, f"Could not start payment: {e}")
        return redirect('subscription:plans')

    authorization_url = result.get('data', {}).get('authorization_url')
    if not authorization_url:
        subscription.status = LandlordSubscription.Status.FAILED
        subscription.save(update_fields=['status'])
        # Same notification pair as above — provider accepted the call but
        # didn't return a usable URL, which is effectively a failed start.
        transaction.on_commit(
            lambda sid=subscription.id: send_payment_failed_email_task.delay(
                sid, reason="Payment provider did not return a payment link."
            )
        )
        transaction.on_commit(
            lambda sid=subscription.id: send_admin_payment_failed_notification_task.delay(
                sid, reason="Payment provider did not return a payment link."
            )
        )
        messages.error(request, "Payment provider did not return a payment link.")
        return redirect('subscription:plans')

    return redirect(authorization_url)


@login_required
def paystack_callback(request):
    reference = request.GET.get('reference') or request.GET.get('trxref')
    if not reference:
        messages.error(request, "Missing payment reference.")
        return redirect('subscription:plans')

    subscription = get_object_or_404(
        LandlordSubscription, payment_reference=reference, landlord=request.user
    )

    if subscription.status == LandlordSubscription.Status.SUCCESS:
        messages.success(request, "Your subscription is active.")
        return redirect('landloards:list_landlord_subscription')

    try:
        result = Paystack().verify_payment(reference)
    except PaystackError as e:
        messages.warning(
            request,
            "We couldn't confirm your payment right now — it will finalize "
            "automatically once confirmed. Check back shortly."
        )
        logger.warning("Callback verify failed for %s: %s", reference, e)
        return redirect('subscription:plans')

    data = result.get('data', {})
    if data.get('status') == 'success':
        _confirm_subscription(subscription)
        messages.success(request, "Payment confirmed — your subscription is active.")
    else:
        failure_reason = (
            data.get('gateway_response')
            or data.get('message')
            or "Payment was not successful."
        )
        subscription.status = LandlordSubscription.Status.FAILED
        subscription.save(update_fields=['status'])
        # Landlord and admin both get notified of failed callbacks.
        transaction.on_commit(
            lambda sid=subscription.id, r=failure_reason:
                send_payment_failed_email_task.delay(sid, reason=r)
        )
        transaction.on_commit(
            lambda sid=subscription.id, r=failure_reason:
                send_admin_payment_failed_notification_task.delay(sid, reason=r)
        )
        messages.error(request, "Payment was not successful.")

    if subscription.status == LandlordSubscription.Status.SUCCESS:
        return redirect('landloards:list_landlord_subscription')
    return redirect('subscription:plans')


@csrf_exempt
@require_POST
def paystack_webhook(request):
    signature = request.headers.get('x-paystack-signature', '')
    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', None)

    if not secret_key:
        logger.error("PAYSTACK_SECRET_KEY missing — cannot verify webhook.")
        return HttpResponse(status=500)

    computed_signature = hmac.new(
        secret_key.encode('utf-8'),
        request.body,
        hashlib.sha512
    ).hexdigest()

    if not hmac.compare_digest(computed_signature, signature):
        logger.warning("Invalid Paystack webhook signature received.")
        return HttpResponse(status=400)

    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_type = event.get('event')
    data = event.get('data', {})
    reference = data.get('reference')

    if event_type == 'charge.success' and reference:
        try:
            subscription = LandlordSubscription.objects.get(payment_reference=reference)
        except LandlordSubscription.DoesNotExist:
            logger.warning("Webhook for unknown reference: %s", reference)
            return HttpResponse(status=200)

        _confirm_subscription(subscription)

    return HttpResponse(status=200)


def _confirm_subscription(subscription):
    with transaction.atomic():
        locked = LandlordSubscription.objects.select_for_update().get(pk=subscription.pk)
        if locked.status == LandlordSubscription.Status.SUCCESS:
            return

        LandlordSubscription.objects.filter(
            landlord=locked.landlord,
            status=LandlordSubscription.Status.SUCCESS,
            is_active=True,
        ).exclude(pk=locked.pk).update(
            is_active=False,
            cancelled_at=timezone.now(),
            end_date=timezone.now(),
        )

        locked.activate()

        # Landlord: subscription-confirmed email
        # Admins: heads-up that a new paying landlord just signed up
        transaction.on_commit(
            lambda: send_subscription_confirmation_email.delay(locked.id)
        )
        transaction.on_commit(
            lambda: send_admin_new_subscription_notification_task.delay(locked.id)
        )


# ---------------------------------------------------------------------------
# Cancel / Reactivate / Change Plan
# ---------------------------------------------------------------------------
@login_required
@require_POST
def cancel_subscription_view(request):
    subscription = get_object_or_404(
        LandlordSubscription,
        landlord=request.user,
        status=LandlordSubscription.Status.SUCCESS,
        is_active=True,
    )
    subscription.cancel(immediate=False)
    transaction.on_commit(
        lambda: send_cancellation_email.delay(subscription.id, immediate=False)
    )
    # Admins should know about churn so support can follow up if appropriate
    transaction.on_commit(
        lambda: send_admin_subscription_cancelled_notification_task.delay(
            subscription.id, immediate=False
        )
    )
    messages.success(
        request,
        f"Your subscription will end on {subscription.end_date:%B %d, %Y}. "
        f"You'll keep full access until then."
    )
    return redirect('landloards:list_landlord_subscription')


@login_required
@require_POST
def reactivate_subscription_view(request):
    subscription = get_object_or_404(
        LandlordSubscription,
        landlord=request.user,
        status=LandlordSubscription.Status.SUCCESS,
        cancel_at_period_end=True,
    )
    try:
        subscription.reactivate()
        transaction.on_commit(
            lambda: send_reactivation_email.delay(subscription.id)
        )
        messages.success(request, "Your subscription has been reactivated.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('landloards:list_landlord_subscription')


@login_required
def change_plan_view(request, plan_id):
    new_plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)

    try:
        result = change_subscription_plan(request.user, new_plan)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('landloards:list_landlord_subscription')

    if result['action'] == 'upgrade':
        return initiate_subscription_payment(request, plan_id)

    transaction.on_commit(
        lambda: send_downgrade_scheduled_email.delay(result['subscription_id'], new_plan.id)
    )
    messages.success(
        request,
        f"Your plan will change to {new_plan.name} on "
        f"{result['effective_date']:%B %d, %Y} — no charge until then."
    )
    return redirect('landloards:list_landlord_subscription')
