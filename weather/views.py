import math
import re
from dataclasses import replace
from functools import partial
from urllib.parse import urlencode

from django.shortcuts import render

from favorites.models import favorite_coordinates

from . import services
from .countries import COUNTRY_CHOICES, COUNTRY_NAMES, country_name
from .openweather import MissingAPIKeyError, OpenWeatherError

MAX_QUERY_LENGTH = 100
MAX_POSTAL_CODE_LENGTH = 20
DEFAULT_POSTAL_COUNTRY = "US"
POSTAL_CODE_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9 -]*")


def _invalid(message):
    return {"kind": "invalid", "message": message}


def _validate_postal_search(postal_code, country_code):
    """Return an error dict for invalid postal search input, or None."""
    if country_code not in COUNTRY_NAMES:
        return _invalid("Choose a country from the list.")
    if len(postal_code) > MAX_POSTAL_CODE_LENGTH:
        return _invalid(f"Postal codes must be {MAX_POSTAL_CODE_LENGTH} characters or fewer.")
    if not POSTAL_CODE_PATTERN.fullmatch(postal_code):
        return _invalid("Postal codes can only contain letters, numbers, spaces, and hyphens.")
    return None


def search(request):
    query = request.GET.get("q", "").strip()
    # Collapse internal whitespace and uppercase, e.g. " sw1a  1aa " -> "SW1A 1AA".
    postal_code = " ".join(request.GET.get("zip", "").split()).upper()
    postal_country = request.GET.get("country", "").strip().upper()
    context = {
        "query": query,
        "postal_code": postal_code,
        "postal_country": postal_country or DEFAULT_POSTAL_COUNTRY,
        "countries": COUNTRY_CHOICES,
        "searched": False,
        "results": [],
        "error": None,
    }

    if postal_code:
        context["search_label"] = f"{postal_code}, {country_name(postal_country)}"
        context["empty_message"] = (
            f"No locations matched postal code {postal_code} in {country_name(postal_country)}. "
            "Check the code and the selected country."
        )
        context["retry_url"] = f"{request.path}?{urlencode({'zip': postal_code, 'country': postal_country})}"
        context["error"] = _validate_postal_search(postal_code, postal_country)
        lookup = partial(services.search_postal_code, postal_code, postal_country)
    elif query:
        context["search_label"] = query
        context["empty_message"] = (
            f"No locations matched “{query}”. Check the spelling or try a nearby city."
        )
        context["retry_url"] = f"{request.path}?{urlencode({'q': query})}"
        if len(query) > MAX_QUERY_LENGTH:
            context["error"] = _invalid(f"Search terms must be {MAX_QUERY_LENGTH} characters or fewer.")
        lookup = partial(services.search_locations, query)
    else:
        lookup = None

    if lookup and not context["error"]:
        try:
            context["results"] = lookup()
            context["searched"] = True
            context["saved_coordinates"] = favorite_coordinates(request.user)
        except MissingAPIKeyError:
            context["error"] = {
                "kind": "missing_key",
                "message": (
                    "Live search is unavailable because no OpenWeather API key "
                    "is configured. Add OPENWEATHER_API_KEY to the .env file "
                    "and restart the server."
                ),
            }
        except OpenWeatherError:
            context["error"] = {
                "kind": "upstream",
                "message": (
                    "We couldn't reach the weather service. "
                    "Please try again or search for a different location."
                ),
            }

    return render(request, "weather/search.html", context)


def _parse_coordinate(raw, limit):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or not -limit <= value <= limit:
        return None
    return services.round_coordinate(value)


def location_from_params(params):
    """Build the selected Location from query params, or None if invalid."""
    lat = _parse_coordinate(params.get("lat"), 90)
    lon = _parse_coordinate(params.get("lon"), 180)
    name = params.get("name", "").strip()
    state = params.get("state", "").strip()
    country = params.get("country", "").strip().upper()
    if lat is None or lon is None:
        return None
    if len(name) > MAX_QUERY_LENGTH or len(state) > MAX_QUERY_LENGTH:
        return None
    if not (len(country) == 2 and country.isalpha()):
        country = ""
    return services.Location(name=name, state=state, country_code=country, lat=lat, lon=lon)


def dashboard(request):
    location = location_from_params(request.GET)
    if location is None:
        return render(request, "weather/dashboard.html", {"invalid": True}, status=400)

    context = {"location": location, "report": None, "error": None, "label": location.label}
    status = 200
    try:
        report = services.get_current_weather(location.lat, location.lon)
    except MissingAPIKeyError:
        status = 503
        context["error"] = {
            "kind": "missing_key",
            "message": (
                "Weather is unavailable because no OpenWeather API key is configured. "
                "Add OPENWEATHER_API_KEY to the .env file and restart the server."
            ),
        }
    except OpenWeatherError:
        status = 503
        context["error"] = {
            "kind": "upstream",
            "message": (
                "We couldn't load the weather for this location. "
                "Please try again or search for a different location."
            ),
        }
    else:
        context["report"] = report
        if not location.name and report.current.place_name:
            context["label"] = ", ".join(
                part for part in (report.current.place_name, location.country) if part
            )

    if not context["label"]:
        context["label"] = f"Latitude {location.lat}, longitude {location.lon}"
    # FR-9: the save form names device-location places after the weather report.
    if not location.name and context["report"]:
        context["favorite_location"] = replace(location, name=context["report"].current.place_name)
    else:
        context["favorite_location"] = location
    context["saved_coordinates"] = favorite_coordinates(request.user)
    context["retry_url"] = f"{request.path}?{request.GET.urlencode()}"
    return render(request, "weather/dashboard.html", context, status=status)
