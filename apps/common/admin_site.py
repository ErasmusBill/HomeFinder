"""
apps/common/admin_site.py

Patches AdminSite.index on the class level so Django admin index view
always injects executive dashboard analytics into context.
"""
import logging
from django.contrib.admin.sites import AdminSite
from apps.common.admin_analytics import get_admin_dashboard_context

logger = logging.getLogger(__name__)

_original_index = AdminSite.index


def custom_admin_index(self, request, extra_context=None):
    extra_context = extra_context or {}
    try:
        dashboard_data = get_admin_dashboard_context(request=request)
        extra_context.update(dashboard_data)
    except Exception as exc:
        logger.exception("Failed to populate admin dashboard analytics: %s", exc)

    return _original_index(self, request, extra_context=extra_context)


def patch_admin_site():
    """Patch AdminSite.index at class level."""
    AdminSite.index = custom_admin_index
