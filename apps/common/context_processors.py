"""
Context processors that inject landlord subscription/trial status into
every template render.

We use a context processor (rather than template tags) so the dashboard
chrome (banner, "Subscribe" button) shows up on every page automatically
without each view having to remember to pass it.
"""


def landlord_subscription_status(request):
    """
    Add a ``landlord_access`` dict to the template context for any
    authenticated landlord (or admin). For non-landlords the dict is
    present but its flags are all False so templates can use it without
    conditionals.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return {"landlord_access": None}

    # Lazy import: avoid a hard dependency on the Subscription app at
    # import time.
    from apps.Subscription.guards import landlord_has_dashboard_access
    from apps.Subscription.models import LandlordSubscription
    from apps.account.models import User

    is_landlord = getattr(user, "role", None) == User.Role.LANDLORD
    is_admin = (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "role", None) == User.Role.ADMIN
    )

    if not (is_landlord or is_admin):
        return {"landlord_access": None}

    has_access = landlord_has_dashboard_access(user)
    trial_active = getattr(user, "is_trial_active", False)
    trial_expired = getattr(user, "is_trial_expired", False)
    days_remaining = getattr(user, "trial_days_remaining", 0) if is_landlord else 0
    # True for landlords who have ever been granted a trial window
    # (whether it's still running or has expired). Used by templates
    # to render a non-misleading banner for landlords who *never* had
    # a trial — those should see a neutral "choose a plan" message
    # rather than the "your trial has ended" copy.
    was_ever_granted_trial = bool(
        getattr(user, "was_ever_granted_trial", False)
    )

    # "Suspended" = landlord whose 30-day trial has ended AND who has no
    # active paid subscription. From the UI's perspective everything on
    # the dashboard is locked until they pay. Note: this only matters
    # for landlords; admins/staff always have full access.
    is_suspended = bool(is_landlord and not has_access)

    # Most-recent active paid subscription, if any — useful so templates
    # can show "Your {plan.name} plan is active until {end_date}".
    active_subscription = None
    if is_landlord:
        active_subscription = (
            LandlordSubscription.objects
            .filter(
                landlord=user,
                status=LandlordSubscription.Status.SUCCESS,
                is_active=True,
                end_date__isnull=False,
            )
            .order_by("-end_date")
            .first()
        )

    return {
        "landlord_access": {
            "is_landlord": is_landlord,
            "is_admin": is_admin,
            "has_access": has_access,
            "trial_active": trial_active,
            "trial_expired": trial_expired,
            "days_remaining": days_remaining,
            "trial_end_date": getattr(user, "trial_end_date", None),
            "active_subscription": active_subscription,
            "is_suspended": is_suspended,
            "was_ever_granted_trial": was_ever_granted_trial,
        }
    }
