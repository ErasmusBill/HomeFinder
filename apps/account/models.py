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

    objects = UserManager()

    REQUIRED_FIELDS = ['full_name', 'phone_number']
    USERNAME_FIELD = 'email'

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