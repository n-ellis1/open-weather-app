from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render, resolve_url
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import TemperatureUnit, set_temperature_unit


def safe_next(request, default=settings.LOGIN_REDIRECT_URL):
    """Return the posted/queried "next" URL if it stays on this site."""
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return resolve_url(default)


def register(request):
    """FR-1: create an account with Django's built-in user model, then sign in."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect(safe_next(request))

    return render(
        request,
        "registration/register.html",
        {"form": form, "next": request.POST.get("next") or request.GET.get("next", "")},
    )


@require_POST
@login_required
def temperature_unit(request):
    """FR-3: save the signed-in user's °C/°F choice and return to the page."""
    unit = request.POST.get("unit", "")
    if unit not in TemperatureUnit.values:
        return HttpResponseBadRequest("Choose Celsius or Fahrenheit.")
    set_temperature_unit(request.user, unit)
    return redirect(safe_next(request))
