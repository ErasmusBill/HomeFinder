import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)

        # Populate full_name if not already populated
        full_name = data.get('name') or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        if full_name:
            user.full_name = full_name

        # OAuth providers like Google verify email addresses
        user.is_email_verified = True

        # Ensure phone_number is None instead of empty string for social logins
        user.phone_number = None

        return user

    def pre_social_login(self, request, sociallogin):
        """
        If a user with this email already exists, connect the social account
        to the existing user instead of failing with a duplicate email error.
        """
        if sociallogin.is_existing:
            return

        email = getattr(sociallogin.user, 'email', None)
        if not email:
            return

        User = get_user_model()
        try:
            existing_user = User.objects.get(email__iexact=email)
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            pass
