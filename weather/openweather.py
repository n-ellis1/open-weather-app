"""Backend-only OpenWeather HTTP client.

All OpenWeather requests go through this module so the API key never reaches
the browser. Error messages and logs never include the request URL, because
the URL carries the API key.
"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

logger = logging.getLogger(__name__)

GEOCODING_DIRECT_URL = "https://api.openweathermap.org/geo/1.0/direct"
GEOCODING_ZIP_URL = "https://api.openweathermap.org/geo/1.0/zip"
CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


class OpenWeatherError(Exception):
    """OpenWeather could not be reached or returned an unusable response."""


class MissingAPIKeyError(OpenWeatherError):
    """No OpenWeather API key is configured."""


class OpenWeatherNotFoundError(OpenWeatherError):
    """OpenWeather returned HTTP 404, e.g. for an unknown postal code."""


class OpenWeatherClient:
    def __init__(self, api_key, timeout=5.0, opener=None):
        self.api_key = api_key
        self.timeout = timeout
        self._opener = opener

    def geocode_city(self, query, limit=5):
        """Return raw OpenWeather geocoding matches for a city name."""
        return self._get_json(GEOCODING_DIRECT_URL, {"q": query, "limit": limit})

    def geocode_zip(self, zip_code, country_code):
        """Return the raw OpenWeather geocoding match for a ZIP/postal code."""
        return self._get_json(GEOCODING_ZIP_URL, {"zip": f"{zip_code},{country_code}"})

    def current_weather(self, lat, lon):
        """Return raw OpenWeather current weather for coordinates, in metric units."""
        return self._get_json(CURRENT_WEATHER_URL, {"lat": lat, "lon": lon, "units": "metric"})

    def _get_json(self, base_url, params):
        if not self.api_key:
            raise MissingAPIKeyError("OpenWeather API key is not configured.")

        url = f"{base_url}?{urlencode({**params, 'appid': self.api_key})}"
        opener = self._opener or urlopen
        try:
            with opener(url, timeout=self.timeout) as response:
                payload = response.read()
        except HTTPError as exc:
            logger.warning("OpenWeather returned HTTP %s for %s", exc.code, base_url)
            error = OpenWeatherNotFoundError if exc.code == 404 else OpenWeatherError
            raise error(f"OpenWeather returned HTTP {exc.code}.") from None
        except (URLError, TimeoutError, OSError) as exc:
            logger.warning("OpenWeather request failed for %s: %s", base_url, type(exc).__name__)
            raise OpenWeatherError("Could not reach OpenWeather.") from None

        try:
            return json.loads(payload)
        except ValueError:
            logger.warning("OpenWeather returned invalid JSON for %s", base_url)
            raise OpenWeatherError("OpenWeather returned an invalid response.") from None
