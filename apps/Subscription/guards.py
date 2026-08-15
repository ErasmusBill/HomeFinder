"""
Access guards for landlord-only actions.

The rule, in plain English:

    A landlord may perform dashboard actions iff EITHER
      (a) they have an active, paid subscription, OR
      (b) they are inside their one-month free trial window.

If neither is true, they are bounced to the subscription plans page with a
message telling them to subscribe. Admins/staff always pass.

The ``subscription_required`` decorator in this module is applied to every
landlord dashboard view (create/update/delete property, upload media,
create amenity, upload documents, etc.). Keep it as a thin shim around
``@login_required`` so the order in views.py is intuitive: login first,
subscription second.

Truth sources:
  * Active paid sub → ``LandlordSubscription`` with status=SUCCESS,
    is_active=True, end_date > now.
  * Active trial → ``User.is_trial_active`` (which checks the
    ``trial_started`` boolean on User; see apps/account/models.py).

Both checks read from the database only when the property needs to
query; the trial property reads columns directly off the user object.
"""

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def _has_active_paid_subscription(user):
    """
    True iff the user has a SUCCESS + is_active + non-expired
    LandlordSubscription row.

    Imported lazily so this module is safe to import from settings.py
    (e.g. context_processors) without dragging the whole Subscription app
    graph in at import time.
    """
    from django.utils import timezone
    from .models import LandlordSubscription

    if not getattr(user, "is_authenticated", False):
        return False

    return LandlordSubscription.objects.filter(
        landlord=user,
        status=LandlordSubscription.Status.SUCCESS,
        is_active=True,
        end_date__gt=timezone.now(),
    ).exists()


def landlord_has_dashboard_access(user):
    """
    The single source of truth for "can this user do landlord work right
    now?". Returns True for:
      - admins / staff (they bypass the gate entirely)
      - landlords with an active paid subscription
      - landlords currently inside their free-trial window

    Order matters: paid subscription is checked first because a
    landlord who subscribed during their trial should keep their access
    even if the trial has since lapsed. The trial is the fallback path,
    not the primary one.
    """
    from apps.account.models import User

    if not getattr(user, "is_authenticated", False):
        return False

    # Admins / staff never get blocked — they're using the dashboard to
    # review work, not to run a business.
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    if getattr(user, "role", None) == User.Role.ADMIN:
        return True

    # Anyone who isn't a landlord at all is also blocked here; the
    # _is_landlord / _is_landlord_or_admin checks in views.py run first
    # in practice, so this is a safety net.
    if getattr(user, "role", None) != User.Role.LANDLORD:
        return False

    if _has_active_paid_subscription(user):
        return True

    # Trial gate. ``is_trial_active`` is False when ``trial_started`` is
    # False (i.e. landlord was never granted a trial) AND when the
    # window has expired — so this single check covers both the "trial
    # running" and "trial already used up" cases without needing a
    # separate is_trial_expired branch here.
    if getattr(user, "is_trial_active", False):
        return True

    return False


def subscription_required(view_func):
    """
    Decorator. Place AFTER @login_required in the view.

    Behaviour:
      - Logged-out users: pass through (login_required handles the bounce).
      - Admins/staff: always allowed.
      - Landlords with active paid sub or active trial: allowed.
      - Everyone else: redirect to the subscription plans page with an
        explanatory flash message.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user

        # login_required runs first; if we get here the user is at least
        # authenticated. We still guard against the anonymous case for
        # direct use without @login_required.
        if not getattr(user, "is_authenticated", False):
            return view_func(request, *args, **kwargs)

        if landlord_has_dashboard_access(user):
            return view_func(request, *args, **kwargs)

        # Distinguish "trial just ended" from "never had one" so the user
        # gets the most useful message.
        if getattr(user, "is_trial_expired", False):
            messages.warning(
                request,
                "Your free trial has ended. Please subscribe to a plan to "
                "continue managing your properties."
            )
        else:
            messages.info(
                request,
                "A subscription is required to use this feature. "
                "Choose a plan to get started."
            )

        return redirect("subscription:plans")

    return _wrapped
