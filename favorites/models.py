from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.db import models

from weather.countries import country_name


class SavedLocation(models.Model):
    """A place someone has saved, identified by its rounded coordinates.

    Coordinates are stored as 4-decimal values (about 11 m), matching the
    rounding used for weather lookups, so two places that share a name (such
    as Paris, Texas and Paris, France) stay separate, and the same place saved
    from search or from the dashboard is one row. Rows are shared by users;
    each user's link to a row is a Favorite.
    """

    lat = models.DecimalField(max_digits=7, decimal_places=4)
    lon = models.DecimalField(max_digits=8, decimal_places=4)
    name = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=2, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lat", "lon"], name="unique_saved_location_coordinates"),
        ]

    @property
    def country(self):
        return country_name(self.country_code)

    # Floats print without trailing zeros (2.32, not 2.3200), matching search.
    @property
    def latitude(self):
        return float(self.lat)

    @property
    def longitude(self):
        return float(self.lon)

    @property
    def label(self):
        """City, state or region, and country; coordinates when unnamed."""
        label = ", ".join(part for part in (self.name, self.state, self.country) if part)
        return label or f"Latitude {self.latitude}, longitude {self.longitude}"

    @property
    def dashboard_query(self):
        """Query string that opens this place in the weather dashboard (FR-10)."""
        return urlencode(
            {
                "lat": self.latitude,
                "lon": self.longitude,
                "name": self.name,
                "state": self.state,
                "country": self.country_code,
            }
        )

    def __str__(self):
        return self.label


class Favorite(models.Model):
    """One user's saved location (FR-9). Each user has at most one per place."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    location = models.ForeignKey(SavedLocation, on_delete=models.CASCADE, related_name="favorites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "location"], name="unique_favorite_per_user"),
        ]

    def __str__(self):
        return f"{self.user}: {self.location}"


def coordinate(value):
    """Store coordinates exactly as the weather service rounds them."""
    return Decimal(str(round(float(value), 4)))


def save_favorite(user, location):
    """Save a services.Location for this user. Returns (favorite, created).

    Saving a place again keeps the single existing entry. A name is filled in
    if the stored place had none (for example, one first saved from device
    coordinates).
    """
    saved, _ = SavedLocation.objects.get_or_create(
        lat=coordinate(location.lat),
        lon=coordinate(location.lon),
        defaults={"name": location.name, "state": location.state, "country_code": location.country_code},
    )
    if not saved.name and location.name:
        saved.name, saved.state, saved.country_code = location.name, location.state, location.country_code
        saved.save(update_fields=["name", "state", "country_code"])
    return Favorite.objects.get_or_create(user=user, location=saved)


def favorite_coordinates(user):
    """Return the set of (lat, lon) floats this user has saved."""
    if not user.is_authenticated:
        return set()
    return {
        (float(lat), float(lon))
        for lat, lon in SavedLocation.objects.filter(favorites__user=user).values_list("lat", "lon")
    }


def remove_favorite(favorite):
    """Delete a favorite, and its place once no user has it saved."""
    location = favorite.location
    favorite.delete()
    if not location.favorites.exists():
        location.delete()
