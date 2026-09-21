import logging
from django import template
from apps.common.admin_analytics import get_admin_dashboard_context

logger = logging.getLogger(__name__)
register = template.Library()


@register.simple_tag(takes_context=True)
def get_admin_dashboard_data(context):
    """
    Template tag that directly computes and returns admin analytics data.
    Takes template context to access the current request and its GET filter parameters.
    """
    request = context.get('request')
    try:
        return get_admin_dashboard_context(request=request)
    except Exception as exc:
        logger.exception("Error in get_admin_dashboard_data template tag: %s", exc)
        return get_admin_dashboard_context(request=None)
