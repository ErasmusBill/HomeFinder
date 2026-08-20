from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from apps.account.forms import LandlordProfileForm
from apps.Subscription.models import SubscriptionPlan
from apps.account.models import User
from apps.account.signals import start_landlord_trial
from django.views.decorators.http import require_POST
from apps.Subscription.guards import _has_active_paid_subscription

@login_required
def onboarding_profile(request):
    """
    Step 1 of Landlord Onboarding: Profile Completion (optional — can be skipped).
    Landlords with an active trial/subscription land here to optionally fill their
    profile; they can proceed straight to the dashboard from here too.
    """
    if request.user.role != User.Role.LANDLORD:
        return redirect('home_finder:home')

    profile = request.user.landlord_profile

    # Handle explicit "Skip" action
    if request.method == 'POST' and 'skip' in request.POST:
        # If they already have a trial/sub, skip straight to dashboard
        from apps.Subscription.guards import _has_active_paid_subscription
        if _has_active_paid_subscription(request.user) or request.user.trial_started:
            return redirect('landloards:landloards_dashboard')
        return redirect('landloards:onboarding_pricing')

    if request.method == 'POST':
        form = LandlordProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved. Let's choose your plan.")
            return redirect('landloards:onboarding_pricing')
    else:
        form = LandlordProfileForm(instance=profile)

    return render(request, 'landloards/onboarding/profile.html', {
        'form': form,
        'hide_trial_banner': True,
    })



@login_required
def onboarding_pricing(request):
    """
    Step 2 of Landlord Onboarding: Pricing / Free Trial
    """
    if request.user.role != User.Role.LANDLORD:
        return redirect('home_finder:home')

    # If they already have a trial or sub, skip to dashboard
    has_sub = _has_active_paid_subscription(request.user)
    if has_sub or request.user.trial_started:
        return redirect('landloards:landloards_dashboard')

    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')

    return render(request, 'landloards/onboarding/pricing.html', {
        'plans': plans,
        'hide_trial_banner': True,
    })


@login_required
@require_POST
def start_free_trial(request):
    """
    Action to explicitly start the 30-day free trial.
    """
    if request.user.role != User.Role.LANDLORD:
        return redirect('dashboard')
        
    if request.user.trial_started:
        messages.info(request, "You have already started your free trial.")
        return redirect('landloards:landloards_dashboard')
        
    try:
        start_landlord_trial(request.user)
        messages.success(request, "Your 30-day free trial has started! Welcome to VacantHommie.")
    except Exception as e:
        messages.error(request, "There was an error starting your free trial. Please contact support.")
        
    return redirect('landloards:landloards_dashboard')
