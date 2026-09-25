import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.urls import reverse

logger = logging.getLogger(__name__)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def _extract_signup_role(self, request, sociallogin=None):
        """
        Extract intended user role from request parameters, session,
        or sociallogin state.
        """
        role = None
        if request:
            role = request.GET.get('role') or request.POST.get('role')
            if not role and hasattr(request, 'session'):
                role = request.session.get('social_signup_role') or request.session.get('signup_role')

        if not role and sociallogin and hasattr(sociallogin, 'state') and isinstance(sociallogin.state, dict):
            role = sociallogin.state.get('role')

        if role:
            role = str(role).lower().strip()
            User = get_user_model()
            if role in {User.Role.LANDLORD, User.Role.TENANT}:
                return role
        return None

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

        # Assign role if specified during social signup (e.g. landlord vs tenant)
        role = self._extract_signup_role(request, sociallogin)
        if role:
            user.role = role

        return user

    def save_user(self, request, sociallogin, form=None):
        """
        Save user and ensure intended role is assigned.
        """
        user = sociallogin.user
        role = self._extract_signup_role(request, sociallogin)
        if role:
            user.role = role

        user = super().save_user(request, sociallogin, form)

        # Clean up session key after user creation
        if request and hasattr(request, 'session') and 'social_signup_role' in request.session:
            try:
                del request.session['social_signup_role']
            except KeyError:
                pass

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

    def get_login_redirect_url(self, request):
        user = getattr(request, 'user', None)
        if user and hasattr(user, 'role'):
            if user.role == 'landlord':
                return reverse('landloards:landloards_dashboard')
            elif user.role == 'tenant':
                return reverse('tenant:dashboard')
            elif user.role == 'admin' or getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
                return '/admin/'
        return '/'

    def get_connect_redirect_url(self, request, socialconnect):
        return self.get_login_redirect_url(request)
