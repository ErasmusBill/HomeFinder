from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """
    Custom user manager to handle creating users and superusers with email,
    full_name, phone_number, and role support.
    """
    def create_user(self, email, full_name, phone_number, password=None, role='tenant', **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')

        if not phone_number:
            raise ValueError('Users must have a phone number')

        email = self.normalize_email(email)

        user = self.model(
            email=email,
            full_name=full_name,
            phone_number=phone_number,
            role=role,
            **extra_fields
        )
        user.set_password(password)
        # Belt-and-braces: the model save() will also enforce this, but
        # setting it here means even code paths that bypass save() (or that
        # inspect the in-memory object before save) see the correct flags.
        if role == 'admin':
            user.is_staff = True
            user.is_superuser = True
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, phone_number, password=None, is_staff=True, is_superuser=True, role='admin', **extra_fields):
        if not email:
            raise ValueError('Superusers must have an email address')
        if not phone_number:
            raise ValueError('Superusers must have a phone number')

        user = self.create_user(
            email=email,
            full_name=full_name,
            phone_number=phone_number,
            password=password,
            role=role,
            **extra_fields
        )
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.save(using=self._db)
        return user