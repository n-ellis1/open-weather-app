from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.views import safe_next
from weather.views import location_from_params

from .models import Favorite, remove_favorite, save_favorite


@login_required
def favorite_list(request):
    """FR-10: the signed-in user's saved locations. No OpenWeather calls."""
    favorites = (
        Favorite.objects.filter(user=request.user)
        .select_related("location")
        .order_by("location__name", "location__state", "location__country_code", "pk")
    )
    return render(request, "favorites/list.html", {"favorites": favorites})


@require_POST
@login_required
def save(request):
    """FR-9: save the posted location for the signed-in user."""
    location = location_from_params(request.POST)
    if location is None:
        return HttpResponseBadRequest("Choose a location from the search results.")
    favorite, created = save_favorite(request.user, location)
    label = favorite.location.label
    if created:
        messages.success(request, f"Saved {label} to your favorites.")
    else:
        messages.info(request, f"{label} is already in your favorites.")
    return redirect(safe_next(request, default="favorites:list"))


@require_POST
@login_required
def remove(request, pk):
    """FR-11: remove one of the signed-in user's favorites (others' are 404)."""
    favorite = get_object_or_404(Favorite.objects.select_related("location"), pk=pk, user=request.user)
    label = favorite.location.label
    remove_favorite(favorite)
    messages.success(request, f"Removed {label} from your favorites.")
    return redirect("favorites:list")
