from django import template

register = template.Library()


@register.filter
def is_saved_by(property_obj, user):
    if not user.is_authenticated or user.role != user.Role.TENANT:
        return False
    return property_obj.saved_by.filter(tenant=user).exists()