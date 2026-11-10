"""Weather service: location lookup, weather retrieval, and caching."""

import math
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as django_timezone

from .countries import country_name
from .openweather import OpenWeatherClient, OpenWeatherError, OpenWeatherNotFoundError
from .us_states import us_state_code

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
    # Set when the location came from a ZIP/postal code search.
    postal_code: str = ""

    @property
    def country(self):
        return country_name(self.country_code)

    @property
    def label(self):
        """City, state or region when available, and country (FR-5)."""
        return ", ".join(part for part in (self.name, self.state, self.country) if part)


def geocoding_query(query):
    """Turn "City, State" into OpenWeather's "City,ST,US" form.

    "Paris, Texas" and "Paris, TX" become "Paris,TX,US". Any other query,
    including an unqualified "Paris", is returned unchanged so OpenWeather
    lists every match.
    """
    parts = query.split(",")
    if len(parts) == 2:
        city, state = parts[0].strip(), us_state_code(parts[1])
        if city and state:
            return f"{city},{state},US"
    return query


def search_locations(query):
    """Return distinct locations matching a city name.

    Raises MissingAPIKeyError or OpenWeatherError when the lookup fails.
    """
    raw_matches = get_client().geocode_city(geocoding_query(query))
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


def search_postal_code(postal_code, country_code):
    """Return the location for a ZIP/postal code in a country, or [] if unknown.

    OpenWeather returns a single match (no state) and HTTP 404 for unknown
    codes. Raises MissingAPIKeyError or OpenWeatherError when the lookup fails.
    """
    try:
        match = get_client().geocode_zip(postal_code, country_code)
    except OpenWeatherNotFoundError:
        return []
    try:
        location = Location(
            name=str(match["name"]),
            state="",
            country_code=str(match.get("country") or country_code),
            lat=round_coordinate(match["lat"]),
            lon=round_coordinate(match["lon"]),
            postal_code=str(match.get("zip") or postal_code),
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise OpenWeatherError("OpenWeather returned an unexpected postal code response.") from None
    return [location]


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


def _cached_report(kind, lat, lon, load):
    """Shared cache policy for current weather and forecasts.

    Reports younger than WEATHER_FRESH_FOR are reused without calling
    OpenWeather (NFR-1). If a refresh fails, the last successful report for
    the same coordinates is returned with is_stale=True (NFR-3).

    `load(lat, lon, fetched_at)` fetches, parses, and builds a new report.
    Raises MissingAPIKeyError or OpenWeatherError when it fails and nothing
    is cached for these coordinates.
    """
    lat, lon = round_coordinate(lat), round_coordinate(lon)
    key = f"weather:{kind}:{lat:.4f}:{lon:.4f}"
    cached = cache.get(key)
    current_time = now()

    if cached and timedelta(0) <= current_time - cached.fetched_at < WEATHER_FRESH_FOR:
        return cached

    try:
        report = load(lat, lon, current_time)
    except OpenWeatherError:
        if cached:
            return replace(cached, is_stale=True)
        raise

    cache.set(key, report, timeout=WEATHER_KEEP_FOR.total_seconds())
    return report


def get_current_weather(lat, lon):
    """Return a cached-or-fresh WeatherReport for coordinates (see _cached_report)."""

    def load(lat, lon, fetched_at):
        current = parse_current_weather(get_client().current_weather(lat, lon))
        return WeatherReport(current=current, fetched_at=fetched_at)

    return _cached_report("current", lat, lon, load)


# /data/2.5/forecast has one sample every 3 hours, so a full local day has 8.
SAMPLES_PER_DAY = 8


@dataclass(frozen=True)
class DailyForecast:
    """One local day estimated from 3-hourly samples, in metric units."""

    date: date
    high: float
    low: float
    description: str
    sample_count: int

    @property
    def is_partial(self):
        """The forecast window doesn't cover the whole local day (FR-8)."""
        return self.sample_count < SAMPLES_PER_DAY

    @property
    def samples_per_day(self):
        return SAMPLES_PER_DAY


@dataclass(frozen=True)
class ForecastReport:
    days: tuple
    fetched_at: datetime
    is_stale: bool = False


def parse_forecast(raw):
    """Group a /data/2.5/forecast response into days by the location's local date.

    Each day's high/low is estimated from the highest temp_max and lowest
    temp_min of its samples, and its conditions are the most common
    description. Samples without a usable time or temperature are skipped.

    Raises OpenWeatherError when no usable samples remain.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("list"), list):
        raise OpenWeatherError("OpenWeather returned an unexpected forecast response.")
    city = raw.get("city") if isinstance(raw.get("city"), dict) else {}
    shift = city.get("timezone")

    grouped = {}
    for item in raw["list"]:
        if not isinstance(item, dict) or not isinstance(item.get("main"), dict):
            continue
        local = _local_time(item.get("dt"), shift)
        main = item["main"]
        temp = _number(main.get("temp"))
        high = _number(main.get("temp_max"))
        low = _number(main.get("temp_min"))
        high = temp if high is None else high
        low = temp if low is None else low
        if local is None or high is None or low is None:
            continue
        conditions = item.get("weather") if isinstance(item.get("weather"), list) else []
        first = conditions[0] if conditions and isinstance(conditions[0], dict) else {}
        grouped.setdefault(local.date(), []).append((high, low, str(first.get("description") or "")))

    if not grouped:
        raise OpenWeatherError("OpenWeather returned an unexpected forecast response.")

    days = []
    for day, samples in sorted(grouped.items()):
        descriptions = Counter(description for _, _, description in samples if description)
        # most_common keeps first-seen order for ties.
        description = descriptions.most_common(1)[0][0] if descriptions else ""
        days.append(
            DailyForecast(
                date=day,
                high=max(high for high, _, _ in samples),
                low=min(low for _, low, _ in samples),
                description=description[:1].upper() + description[1:],
                sample_count=len(samples),
            )
        )
    return tuple(days)


def get_forecast(lat, lon):
    """Return a cached-or-fresh ForecastReport for coordinates (see _cached_report)."""

    def load(lat, lon, fetched_at):
        days = parse_forecast(get_client().forecast(lat, lon))
        return ForecastReport(days=days, fetched_at=fetched_at)

    return _cached_report("forecast", lat, lon, load)
