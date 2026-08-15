from django.contrib.auth import authenticate, login, logout, get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from .forms import (
    RegisterUserForm,
    TenantProfileForm,
    LandlordProfileForm,
    PasswordResetForm,
    ResetPasswordConfirmForm,
    ChangePasswordForm, UserProfileForm
)
from .tasks import send_activation_email_task, send_password_reset_email_task
from .models import TenantProfile, LandlordProfile

User = get_user_model()


def _get_profile_for_user(user):
    """Return the user's role-specific profile, creating a missing one.

    Profiles are normally created by the User post-save signal.  Existing
    accounts and accounts whose role was changed before that signal existed
    may not have one, however, so views must not assume the reverse one-to-one
    relation is always present.
    """
    if user.role == User.Role.LANDLORD:
        profile, _ = LandlordProfile.objects.get_or_create(user=user)
        return profile, LandlordProfileForm
    if user.role == User.Role.TENANT:
        profile, _ = TenantProfile.objects.get_or_create(user=user)
        return profile, TenantProfileForm
    return None, None


def _should_auto_redirect_to_paystack(user):
    """
    Return True iff this landlord should be sent straight to Paystack on
    login (no manual click on a pricing plan needed).

    The rule: the landlord is logging in for the first time to manage
    properties — i.e. they have never even attempted a payment. We treat
    that as "no LandlordSubscription row at all", regardless of status.
    Once they have at least one PENDING or FAILED attempt, we stop
    force-redirecting and let them land on the dashboard / pricing page
    on their own terms (so they can re-pick a plan, browse, etc.).

    Free trial windows are intentionally NOT consulted here — the trial
    is what lets them *use* the dashboard during this redirect; the
    redirect is about collecting payment before they get distracted.
    Admins/staff and non-landlords always return False.
    """
    from apps.Subscription.models import LandlordSubscription

    if not getattr(user, "is_authenticated", False):
        return False
    if user.role != User.Role.LANDLORD:
        return False
    if user.is_staff or user.is_superuser:
        return False

    return not LandlordSubscription.objects.filter(landlord=user).exists()


def register_view(request):
    if request.method == 'POST':
        form = RegisterUserForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            send_activation_email_task.delay(user.id)

            messages.success(request, 'Account created successfully! Please check your email to activate your account.')
            return redirect('account:login')
    else:
        form = RegisterUserForm()

    context = {
        'form': form
    }
    return render(request, 'account/register.html', context)


def login_view(request):
    if request.method == 'POST':
        identifier = request.POST.get('identifier')
        password = request.POST.get('password')

        if not identifier or not password:
            messages.error(request, 'Please enter your identifier and password.')
            return redirect('account:login')

        user = authenticate(request, email=identifier, password=password)

        if user is not None:
            if user.is_email_verified and user.is_active:
                login(request, user)

                # First-time landlord: no LandlordSubscription row yet.
                # Skip the "click a plan on the pricing page" step and
                # take them straight to Paystack for the default plan so
                # they can pay and immediately start using the dashboard.
                # The free trial is already running on the User row
                # (set by signals.create_user_profile), so they aren't
                # blocked from the dashboard during this redirect — they
                # just see the Paystack page first.
                # if _should_auto_redirect_to_paystack(user):
                #     from apps.Subscription.services import get_default_paid_plan
                #     default_plan = get_default_paid_plan()
                #     if default_plan is not None:
                #         return redirect(
                #             reverse(
                #                 'subscription:initiate_payment',
                #                 kwargs={'plan_id': default_plan.id},
                #             )
                #         )
                    # No paid plan on the system — fall through to the
                    # normal dashboard redirect and let them pick.

                # Strict role-based redirection
                role_val = getattr(user, 'role', None)
                if role_val == User.Role.TENANT or role_val == 'tenant':
                    return redirect('tenant-dashboard')
                elif role_val == User.Role.LANDLORD or role_val == 'landlord':
                    return redirect('landloards:landloards_dashboard')
                elif role_val == User.Role.ADMIN or role_val == 'admin' or user.is_staff or user.is_superuser:
                    return redirect('/admin/')
                else:
                    return redirect('dashboard')
            else:
                messages.error(request, 'Your account is disabled or your email is not verified.')
                return redirect('account:login')
        else:
            messages.error(request, 'Invalid email/phone number or password.')
            return redirect('account:login')

    return render(request, 'account/login.html')


@login_required
def user_logout(request):
    logout(request)
    return redirect('home_finder:home')


@login_required
def update_profile_view(request):
    user = request.user
    profile, form_class = _get_profile_for_user(user)
    if profile is None:
        messages.error(request, "Admins do not have a standard profile view.")
        return redirect('/admin/')

    if request.method == 'POST':
        # Pass request.FILES so profile pictures are correctly uploaded and updated
        form = form_class(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('update_profile')
    else:
        form = form_class(instance=profile)

    context = {
        'form': form,
        'profile': profile
    }
    return render(request, 'account/update_profile.html', context)


def forgot_password_view(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            associated_users = User.objects.filter(email__iexact=email, is_active=True)

            for user in associated_users:
                # Fire the Celery background task asynchronously
                send_password_reset_email_task.delay(user.id)

            messages.success(
                request,
                'If an account with that email exists, we have sent instructions to reset your password.'
            )
            return redirect('login')
    else:
        form = PasswordResetForm()

    return render(request, 'account/forgot_password.html', {'form': form})


def reset_password_confirm_view(request):
    uidb64 = request.GET.get('uid') or request.POST.get('uid')
    token = request.GET.get('token') or request.POST.get('token')

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = ResetPasswordConfirmForm(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Your password has been reset successfully. You can now log in.')
                return redirect('login')
        else:
            form = ResetPasswordConfirmForm(user)

        return render(
            request,
            'account/reset_password_confirm.html',
            {'form': form, 'uid': uidb64, 'token': token}
        )
    else:
        messages.error(request, 'The password reset link is invalid or has expired.')
        return redirect('login')


def verify_email_view(request):
    from .tokens import email_verification_token
    uidb64 = request.GET.get('uid') or request.POST.get('uid')
    token = request.GET.get('token') or request.POST.get('token')
    
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and email_verification_token.check_token(user, token):
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])
        messages.success(request, 'Your email has been verified successfully. You can now log in.')
        return redirect('account:login')
    else:
        messages.error(request, 'The activation link is invalid or has expired.')
        return redirect('account:login')


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = ChangePasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')

            role_val = getattr(user, 'role', None)
            if role_val == User.Role.TENANT or role_val == 'tenant':
                return redirect('tenant-dashboard')
            elif role_val == User.Role.LANDLORD or role_val == 'landlord':
                return redirect('landlord-dashboard')
            elif role_val == User.Role.ADMIN or role_val == 'admin' or user.is_staff or user.is_superuser:
                return redirect('/admin/')
            else:
                return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = ChangePasswordForm(user=request.user)

    context = {
        'form': form
    }
    return render(request, 'account/change_password.html', context)

@login_required
def account_settings_view(request):
    user = request.user
    user_form = UserProfileForm(instance=user)
    profile, profile_form_class = _get_profile_for_user(user)

    if user.role == User.Role.LANDLORD:
        template = "landloards/account/settings.html"
    elif user.role == User.Role.TENANT:
        # Tenant settings have not yet got a dedicated page.  Keep the
        # endpoint safe and render the generic template in the meantime.
        template = "account/settings.html"
    else:
        messages.error(request, "Admins manage their account settings in the admin site.")
        return redirect("/admin/")

    password_form = ChangePasswordForm(user=user)

    return render(
        request,
        template,
        {
            "user_form": user_form,
            "profile_form": profile_form_class(instance=profile),
            "password_form": password_form,
        },
    )

@login_required
def update_personal_information(request):
    if request.method != "POST":
        return redirect("account:settings")

    form = UserProfileForm(
        request.POST,
        instance=request.user,
    )

    if form.is_valid():
        form.save()
        messages.success(
            request,
            "Personal information updated successfully.",
        )
    else:
        messages.error(
            request,
            "Please correct the errors below.",
        )

    return redirect("account:settings")


@login_required
def update_profile_information(request):
    if request.method != "POST":
        return redirect("account:settings")

    user = request.user
    profile, form_class = _get_profile_for_user(user)
    if profile is None:
        messages.error(request, "Admins do not have a standard profile.")
        return redirect("/admin/")

    form = form_class(request.POST, request.FILES, instance=profile)

    if form.is_valid():
        form.save()
        messages.success(
            request,
            "Profile updated successfully.",
        )
    else:
        messages.error(
            request,
            "Please correct the errors below.",
        )

    return redirect("account:settings")
