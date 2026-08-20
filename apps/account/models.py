from django.db import models
from apps.common.models import BaseModel
from django.contrib.auth.models import AbstractUser
from .manager import UserManager


class User(BaseModel, AbstractUser):

    class Role(models.TextChoices):
        TENANT = 'tenant', 'Tenant'
        LANDLORD = 'landlord', 'Landlord'
        ADMIN = 'admin', 'Admin'

    username = None

    full_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, unique=True)
    phone_number = models.CharField(max_length=30, unique=True)
    is_email_verified = models.BooleanField(default=False)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TENANT)

    email_property_alerts = models.BooleanField(
        default=True,
        help_text=(
            "If True, the tenant receives an email when a new property "
            "matches one of their saved PropertyAlert rows. The in-app "
            "notification is always created regardless of this flag — "
            "the email is the only thing this controls."
        ),
    )

    trial_started = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "True once this landlord has been granted a free trial. "
            "Stays True forever — even after the trial ends — so the "
            "guard, dashboard and emails can distinguish 'never had a "
            "trial' from 'trial ran out'."
        ),
    )
    trial_start_date = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )
    notified_trial_ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Set by the daily beat task the first time the "
            "'your trial has ended' email is dispatched. NULL means "
            "no such email has been sent yet."
        ),
    )

    @property
    def is_trial_active(self):
        """
        True iff the user is a landlord whose trial window is currently
        running (trial_started=True, trial_end_date is in the future).
        Reads the columns directly so a freshly-fetched user object is
        enough — no extra DB hit.
        """
        from django.utils import timezone
        if self.role != self.Role.LANDLORD:
            return False
        if not self.trial_started or not self.trial_end_date:
            return False
        return self.trial_end_date > timezone.now()

    @property
    def is_trial_expired(self):
        """
        True iff the user is a landlord whose trial was started but has
        already ended. Used to distinguish "never had a trial" from
        "trial ran out" — they get the same UX for blocked actions, but
        a different dashboard message.
        """
        from django.utils import timezone
        if self.role != self.Role.LANDLORD:
            return False
        if not self.trial_started or not self.trial_end_date:
            return False
        return self.trial_end_date <= timezone.now()

    @property
    def was_ever_granted_trial(self):
        """
        True iff this user is a landlord who has ever been granted a
        free trial (regardless of whether it's still running or has
        expired). Used by templates to render a non-misleading
        banner for landlords who never had a trial.
        """
        return self.role == self.Role.LANDLORD and bool(self.trial_started)

    @property
    def trial_days_remaining(self):
        """
        Whole days (rounded up) left in the free trial, or 0 if not
        active. ``timedelta.days`` rounds down, which on the final day
        reports 0 even when there are hours left — so we use
        ``math.ceil`` on the total seconds for an honest "1 day left"
        on the last day, "2 days left" with 24-48h remaining, etc.
        """
        import math
        from django.utils import timezone
        if not self.is_trial_active:
            return 0
        delta = self.trial_end_date - timezone.now()
        # Ceil(total_seconds / 86400) gives the number of full days
        # remaining, never less than 1 while the trial is still active.
        return max(1, math.ceil(delta.total_seconds() / 86400))

    objects = UserManager()

    REQUIRED_FIELDS = ['full_name', 'phone_number']
    USERNAME_FIELD = 'email'

    def save(self, *args, **kwargs):
        """
        Enforce a single rule: any user with role='admin' is automatically
        a Django superuser and has staff access. This keeps the data layer
        consistent so admins can never exist without admin-backend privileges
        and so background tasks that look at is_superuser / is_staff don't
        miss a "role=admin but not superuser" row.
        """
        if self.role == self.Role.ADMIN:
            self.is_staff = True
            self.is_superuser = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} - {self.email}"


class TenantProfile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tenant_profile')
    profile_picture = models.ImageField(upload_to='profiles/tenants/', blank=True, null=True)
    emergency_contact_name = models.CharField(max_length=255, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True, null=True)
    employer_name = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Tenant Profile: {self.user.full_name}"


class LandlordProfile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='landlord_profile')
    profile_picture = models.ImageField(upload_to='profiles/landlords/', blank=True, null=True)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    tax_identification_number = models.CharField(max_length=100, blank=True, null=True)
    payout_bank_account = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Landlord Profile: {self.user.full_name}"