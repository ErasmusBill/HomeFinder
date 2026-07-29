from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class EmailOrPhoneBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using
    either their email address or phone number, along with their password.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get('email') or kwargs.get('phone_number')

        if not identifier or not password:
            return None

        try:
            user = User.objects.get(
                models.Q(email__iexact=identifier) |
                models.Q(phone_number__iexact=identifier)
            )
        except User.DoesNotExist:
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None