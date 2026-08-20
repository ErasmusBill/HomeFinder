from django import template
from django.utils import timezone
from django.utils.timesince import timesince

register = template.Library()


@register.filter
def is_saved_by(property_obj, user):
    if not user.is_authenticated or user.role != user.Role.TENANT:
        return False
    return property_obj.saved_by.filter(tenant=user).exists()


@register.filter
def timeago(dt):
    """Returns a short human-readable "time ago" string (e.g. '2h', '3d', '5w')."""
    if not dt:
        return ""
    delta = timezone.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 604800:
        return f"{seconds // 86400}d ago"
    if seconds < 2592000:
        return f"{seconds // 604800}w ago"
    # Fall back to Django's full phrase for older items.
    return f"{timesince(dt).split(',')[0]} ago"


@register.filter
def ghana_money(amount):
    """Formats a numeric value as 'GH₵ 1,234.00'."""
    if amount is None or amount == "":
        return ""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    # Use comma grouping without decimals for whole numbers, otherwise 2 dp.
    if value.is_integer():
        return f"GH₵ {int(value):,}"
    return f"GH₵ {value:,.2f}"


@register.filter
def get_item(dictionary, key):
    """Dictionary lookup for templates where a dot-lookup isn't possible."""
    if not dictionary:
        return None
    try:
        return dictionary.get(key)
    except AttributeError:
        try:
            return dictionary[key]
        except (KeyError, TypeError, IndexError):
            return None


@register.filter
def status_badge_class(status):
    """Maps a viewing-request status string to Tailwind badge classes."""
    return {
        "pending": "bg-amber-100 text-amber-800",
        "confirmed": "bg-emerald-100 text-emerald-800",
        "completed": "bg-blue-100 text-blue-800",
        "cancelled": "bg-gray-200 text-gray-700",
    }.get(status, "bg-gray-100 text-gray-700")


@register.filter
def room_type_display(value):
    """Pretty-print the room_type choice (e.g. 'self_contained' -> 'Self Contained')."""
    if not value:
        return ""
    return str(value).replace("_", " ").title()