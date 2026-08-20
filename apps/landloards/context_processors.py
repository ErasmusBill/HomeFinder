"""
Context processors that inject landlord viewing-request data into
every template render.

Currently this exposes only ``landlord_viewing_pending_count`` so the
sidebar badge can show how many viewing requests are awaiting a
response. Anything else a landlord template needs globally belongs
here so individual views don't have to remember to pass it.
"""


def landlord_viewing_request_counts(request):
    """
    Add a ``landlord_viewing_pending_count`` int to the template
    context for any authenticated landlord (or admin). For everyone
    else the key is present but ``0`` so templates can render the
    sidebar badge unconditionally.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return {"landlord_viewing_pending_count": 0}

    from apps.account.models import User

    is_landlord = getattr(user, "role", None) == User.Role.LANDLORD
    is_admin = (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "role", None) == User.Role.ADMIN
    )
    if not (is_landlord or is_admin):
        return {"landlord_viewing_pending_count": 0}

    # Lazy imports: avoid circular import at module load time
    # (``selectors`` imports ``tenant.models.ViewingRequest``).
    from apps.landloards.selectors import get_landlord_viewing_request_counts

    counts = get_landlord_viewing_request_counts(user)
    return {
        "landlord_viewing_pending_count": int(counts.get("pending_count", 0) or 0),
        "landlord_viewing_confirmed_count": int(counts.get("confirmed_count", 0) or 0),
    }
