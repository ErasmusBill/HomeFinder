from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from apps.account.models import User

def onboarding_required(view_func):
    """
    Decorator for landlord views to ensure they have completed the SaaS onboarding.
    Only blocks access if the landlord has neither started a trial nor has an
    active subscription. Profile details (company name, photo) are optional and
    no longer required to proceed.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user

        # If not authenticated, let login_required handle it.
        if not getattr(user, "is_authenticated", False):
            return view_func(request, *args, **kwargs)

        # Admins and non-landlords bypass this guard entirely
        if getattr(user, "role", None) != User.Role.LANDLORD:
            return view_func(request, *args, **kwargs)

        # Check trial/subscription — the only hard requirement to access the dashboard
        from apps.Subscription.guards import _has_active_paid_subscription

        has_sub = _has_active_paid_subscription(user)
        has_trial = getattr(user, "trial_started", False)

        if not has_sub and not has_trial:
            url_name = getattr(request.resolver_match, "url_name", None)
            if url_name not in ("onboarding_profile", "onboarding_pricing", "start_free_trial"):
                messages.info(request, "Please select a plan or start your free trial to access the dashboard.")
                return redirect("landloards:onboarding_profile")

        return view_func(request, *args, **kwargs)

    return _wrapped
