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
