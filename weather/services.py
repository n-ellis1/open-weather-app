"""Weather service: location lookup (and later weather retrieval and caching)."""

from dataclasses import dataclass

from django.conf import settings

from .countries import country_name
from .openweather import OpenWeatherClient, OpenWeatherError


def get_client():
    """Build the backend OpenWeather client from settings."""
    return OpenWeatherClient(
        api_key=settings.OPENWEATHER_API_KEY,
        timeout=settings.OPENWEATHER_TIMEOUT_SECONDS,
    )


@dataclass(frozen=True)
class Location:
    name: str
    state: str
    country_code: str
    lat: float
    lon: float

    @property
    def country(self):
        return country_name(self.country_code)

    @property
    def label(self):
        """City, state or region when available, and country (FR-5)."""
        return ", ".join(part for part in (self.name, self.state, self.country) if part)


def search_locations(query):
    """Return distinct locations matching a city name.

    Raises MissingAPIKeyError or OpenWeatherError when the lookup fails.
    """
    raw_matches = get_client().geocode_city(query)
    if not isinstance(raw_matches, list):
        raise OpenWeatherError("OpenWeather returned an unexpected search response.")

    locations = []
    seen = set()
    for match in raw_matches:
        try:
            location = Location(
                name=str(match["name"]),
                state=str(match.get("state") or ""),
                country_code=str(match.get("country") or ""),
                lat=round(float(match["lat"]), 4),
                lon=round(float(match["lon"]), 4),
            )
        except (KeyError, TypeError, ValueError):
            continue
        key = (location.name, location.state, location.country_code, location.lat, location.lon)
        if key in seen:
            continue
        seen.add(key)
        locations.append(location)
    return locations
