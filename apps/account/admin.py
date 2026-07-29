from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, TenantProfile, LandlordProfile


class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('email', 'full_name', 'phone_number', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active', 'is_email_verified')
    search_fields = ('email', 'full_name', 'phone_number')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('full_name', 'phone_number')}),
        ('Permissions & Roles', {
            'fields': ('role', 'is_email_verified', 'is_active', 'is_staff', 'is_superuser', 'groups',
                       'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'phone_number', 'password1', 'password2', 'role')}
         ),
    )


admin.site.register(User, CustomUserAdmin)
admin.site.register(TenantProfile)
admin.site.register(LandlordProfile)