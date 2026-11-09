"""Weather service: location lookup, weather retrieval, and caching."""

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as django_timezone

from .countries import country_name
from .openweather import OpenWeatherClient, OpenWeatherError

# Successful weather is reused without an upstream call for this long (NFR-1).
WEATHER_FRESH_FOR = timedelta(minutes=10)
# The last successful weather is kept this long as a fallback for upstream
# failures (NFR-3).
WEATHER_KEEP_FOR = timedelta(hours=24)


def now():
    """Current time; tests patch this to control the cache clock."""
    return django_timezone.now()


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


def round_coordinate(value):
    """Coordinates are rounded to 4 decimals (~11 m) for lookups and cache keys."""
    return round(float(value), 4)


@dataclass(frozen=True)
class CurrentWeather:
    """Current conditions in metric units. Optional fields are None when missing."""

    temperature: float
    feels_like: float | None
    humidity: int | None
    wind_speed: float | None
    cloud_cover: int | None
    pressure: int | None
    description: str
    # Naive datetimes in the location's local time, so templates don't
    # convert them to the server time zone.
    sunrise: datetime | None
    sunset: datetime | None
    place_name: str
    # Not included in OpenWeather's /data/2.5/weather response.
    uv_index: float | None = None


@dataclass(frozen=True)
class WeatherReport:
    current: CurrentWeather
    fetched_at: datetime
    is_stale: bool = False


def _number(value, cast=float):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return cast(round(value)) if cast is int else cast(value)


def _local_time(timestamp, shift_seconds):
    if _number(timestamp) is None:
        return None
    shift = _number(shift_seconds, int) or 0
    aware = datetime.fromtimestamp(timestamp, tz=timezone.utc) + timedelta(seconds=shift)
    return aware.replace(tzinfo=None)


def parse_current_weather(raw):
    """Turn a /data/2.5/weather response into CurrentWeather.

    Raises OpenWeatherError when the response has no usable temperature.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("main"), dict):
        raise OpenWeatherError("OpenWeather returned an unexpected weather response.")
    main = raw["main"]
    temperature = _number(main.get("temp"))
    if temperature is None:
        raise OpenWeatherError("OpenWeather returned an unexpected weather response.")

    wind = raw.get("wind") if isinstance(raw.get("wind"), dict) else {}
    clouds = raw.get("clouds") if isinstance(raw.get("clouds"), dict) else {}
    sys = raw.get("sys") if isinstance(raw.get("sys"), dict) else {}
    conditions = raw.get("weather") if isinstance(raw.get("weather"), list) else []
    first = conditions[0] if conditions and isinstance(conditions[0], dict) else {}
    description = str(first.get("description") or "")

    return CurrentWeather(
        temperature=temperature,
        feels_like=_number(main.get("feels_like")),
        humidity=_number(main.get("humidity"), int),
        wind_speed=_number(wind.get("speed")),
        cloud_cover=_number(clouds.get("all"), int),
        pressure=_number(main.get("pressure"), int),
        description=description[:1].upper() + description[1:],
        sunrise=_local_time(sys.get("sunrise"), raw.get("timezone")),
        sunset=_local_time(sys.get("sunset"), raw.get("timezone")),
        place_name=str(raw.get("name") or ""),
    )


def get_current_weather(lat, lon):
    """Return a WeatherReport for coordinates.

    Cached weather younger than WEATHER_FRESH_FOR is reused without calling
    OpenWeather (NFR-1). If a refresh fails, the last successful weather for
    the same coordinates is returned with is_stale=True (NFR-3).

    Raises MissingAPIKeyError or OpenWeatherError when the lookup fails and no
    cached weather exists for these coordinates.
    """
    lat, lon = round_coordinate(lat), round_coordinate(lon)
    key = f"weather:current:{lat:.4f}:{lon:.4f}"
    cached = cache.get(key)
    current_time = now()

    if cached and timedelta(0) <= current_time - cached.fetched_at < WEATHER_FRESH_FOR:
        return cached

    try:
        current = parse_current_weather(get_client().current_weather(lat, lon))
    except OpenWeatherError:
        if cached:
            return replace(cached, is_stale=True)
        raise

    report = WeatherReport(current=current, fetched_at=current_time)
    cache.set(key, report, timeout=WEATHER_KEEP_FOR.total_seconds())
    return report
