import math

from django.shortcuts import render

from . import services
from .openweather import MissingAPIKeyError, OpenWeatherError

MAX_QUERY_LENGTH = 100


def search(request):
    query = request.GET.get("q", "").strip()
    context = {"query": query, "searched": False, "results": [], "error": None}

    if query:
        if len(query) > MAX_QUERY_LENGTH:
            context["error"] = {
                "kind": "invalid",
                "message": f"Search terms must be {MAX_QUERY_LENGTH} characters or fewer.",
            }
        else:
            try:
                context["results"] = services.search_locations(query)
                context["searched"] = True
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


def _location_from_params(params):
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
    location = _location_from_params(request.GET)
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
    context["retry_url"] = f"{request.path}?{request.GET.urlencode()}"
    return render(request, "weather/dashboard.html", context, status=status)
