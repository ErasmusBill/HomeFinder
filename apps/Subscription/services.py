import logging
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    """Raised when a Paystack request fails or returns an unexpected response."""
    pass


class Paystack:
    def __init__(self, data=None):
        self.secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', None)
        if not self.secret_key:
            raise PaystackError("PAYSTACK_SECRET_KEY is not configured in settings.")
        self.base_url = "https://api.paystack.co"
        self.content_type = 'application/json'
        self.data = data or {}
        self.timeout = 15  # seconds — never let a payment call hang forever

    @property
    def headers(self):
        return {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': self.content_type,
        }

    def _request(self, method, url, **kwargs):
        try:
            response = requests.request(
                method, url, headers=self.headers, timeout=self.timeout, **kwargs
            )
        except requests.exceptions.Timeout:
            logger.error("Paystack request timed out: %s %s", method, url)
            raise PaystackError("Payment provider timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            logger.error("Paystack connection error: %s %s", method, url)
            raise PaystackError("Could not reach payment provider. Please try again.")
        except requests.exceptions.RequestException as e:
            logger.error("Paystack request failed: %s %s | %s", method, url, e)
            raise PaystackError("Payment provider request failed.")

        try:
            payload = response.json()
        except ValueError:
            logger.error(
                "Paystack returned non-JSON response (%s): %s",
                response.status_code, response.text[:500]
            )
            raise PaystackError("Payment provider returned an invalid response.")

        if response.status_code not in (200, 201):
            logger.warning(
                "Paystack error response (%s): %s", response.status_code, payload
            )
            raise PaystackError(payload.get('message', 'Payment request failed.'))

        return payload

    def initiate_payment(self):
        url = f"{self.base_url}/transaction/initialize"
        return self._request('POST', url, json=self.data)

    def verify_payment(self, reference):
        url = f"{self.base_url}/transaction/verify/{reference}"
        return self._request('GET', url)


# ---------------------------------------------------------------------------
# Plan change logic
# ---------------------------------------------------------------------------

def _get_active_subscription(landlord):
    """
    Local import to avoid a circular import between services.py and models.py
    at module load time.
    """
    from .models import LandlordSubscription

    return (
        LandlordSubscription.objects
        .filter(
            landlord=landlord,
            status=LandlordSubscription.Status.SUCCESS,
            is_active=True,
        )
        .order_by('-end_date')
        .first()
    )


def change_subscription_plan(landlord, new_plan):
    """
    Decide what should happen when a landlord with an active subscription
    picks a different plan, and apply the non-payment side of that decision.

    Returns a dict describing what happened:
        {'action': 'upgrade', 'subscription_id': <uuid>}
            - Caller (change_plan_view) is expected to immediately redirect
              into initiate_subscription_payment for the new plan. Nothing
              is changed here — the old subscription stays active/SUCCESS
              until _confirm_subscription() closes it out after payment.

        {'action': 'downgrade', 'subscription_id': <uuid>, 'effective_date': <datetime>}
            - No payment needed. The current subscription keeps running
              until its end_date, at which point the pending_plan should
              be applied (e.g. by a scheduled task) instead of renewing
              onto the same plan.

    Raises ValueError if there's nothing sensible to "change" — e.g. no
    active subscription exists yet, or the landlord picked the plan
    they're already on.
    """
    active_subscription = _get_active_subscription(landlord)

    if active_subscription is None:
        raise ValueError(
            "You don't have an active subscription to change. "
            "Please subscribe to a plan first."
        )

    current_plan = active_subscription.plan

    if current_plan.id == new_plan.id:
        raise ValueError(f"You're already subscribed to the {new_plan.name} plan.")

    if new_plan.price > current_plan.price:
        # Upgrade: charge now, take effect immediately once payment is
        # confirmed. We deliberately don't touch the current subscription
        # here — _confirm_subscription() will deactivate it once the new
        # one succeeds, so a failed/abandoned payment leaves the landlord
        # exactly where they were.
        return {
            'action': 'upgrade',
            'subscription_id': str(active_subscription.id),
        }

    # Downgrade (or lateral move to a cheaper/equal-listing plan): no
    # charge, scheduled for the end of the current billing period.
    with transaction.atomic():
        locked = (
            type(active_subscription).objects
            .select_for_update()
            .get(pk=active_subscription.pk)
        )
        locked.schedule_plan_change(new_plan)

    return {
        'action': 'downgrade',
        'subscription_id': str(active_subscription.id),
        'effective_date': active_subscription.end_date,
    }