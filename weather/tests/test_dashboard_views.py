from datetime import datetime, timedelta, timezone
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from weather.openweather import MissingAPIKeyError, OpenWeatherError

from .test_search_views import PARIS_MATCHES

T0 = datetime(2026, 11, 9, 14, 5, tzinfo=timezone.utc)

TEXAS = {"lat": "33.6618", "lon": "-95.5555", "name": "Paris", "state": "Texas", "country": "US"}
FRANCE = {"lat": "48.8589", "lon": "2.32", "name": "Paris", "state": "Ile-de-France", "country": "FR"}


def current_payload(temp, *, name="Paris", feels_like=None, tz_shift=0):
    """Shaped like an OpenWeather /data/2.5/weather response (units=metric)."""
    return {
        "coord": {"lon": 0, "lat": 0},
        "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
        "main": {
            "temp": temp,
            "feels_like": temp - 1 if feels_like is None else feels_like,
            "pressure": 1016,
            "humidity": 41,
        },
        "wind": {"speed": 4.12, "deg": 200},
        "clouds": {"all": 20},
        "dt": 1794233100,
        # 2026-11-09 12:30 and 23:15 UTC.
        "sys": {"country": "US", "sunrise": 1794227400, "sunset": 1794266100},
        "timezone": tz_shift,
        "name": name,
        "cod": 200,
    }


class DashboardTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

        patcher = mock.patch("weather.services.get_client")
        self.client_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

        self.clock = T0
        clock_patcher = mock.patch("weather.services.now", side_effect=lambda: self.clock)
        clock_patcher.start()
        self.addCleanup(clock_patcher.stop)

    def get_dashboard(self, params):
        return self.client.get(reverse("weather:dashboard"), params)


class SelectLocationTests(DashboardTestCase):
    def test_search_results_link_to_dashboard_with_each_matchs_coordinates(self):
        self.client_mock.geocode_city.return_value = PARIS_MATCHES

        response = self.client.get(reverse("weather:search"), {"q": "Paris"})

        dashboard = reverse("weather:dashboard")
        self.assertContains(
            response,
            f'href="{dashboard}?lat=33.6618&amp;lon=-95.5555&amp;name=Paris&amp;state=Texas&amp;country=US"',
        )
        self.assertContains(
            response,
            f'href="{dashboard}?lat=48.8589&amp;lon=2.32&amp;name=Paris&amp;state=Ile-de-France&amp;country=FR"',
        )

    def test_selecting_texas_result_shows_texas_weather_using_its_coordinates(self):
        def by_coordinates(lat, lon):
            return current_payload(31.4) if (lat, lon) == (33.6618, -95.5555) else current_payload(8.2)

        self.client_mock.current_weather.side_effect = by_coordinates

        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 200)
        self.client_mock.current_weather.assert_called_once_with(33.6618, -95.5555)
        self.assertContains(response, "Paris, Texas, United States")
        self.assertContains(response, "31°C")
        self.assertNotContains(response, "8°C")

    def test_same_named_cities_load_and_cache_separately(self):
        self.client_mock.current_weather.side_effect = [current_payload(31.4), current_payload(8.2)]

        texas = self.get_dashboard(TEXAS)
        france = self.get_dashboard(FRANCE)

        self.assertContains(texas, "31°C")
        self.assertContains(france, "Paris, Ile-de-France, France")
        self.assertContains(france, "8°C")
        self.assertEqual(
            self.client_mock.current_weather.call_args_list,
            [mock.call(33.6618, -95.5555), mock.call(48.8589, 2.32)],
        )

    def test_dashboard_shows_current_weather_details(self):
        self.client_mock.current_weather.return_value = current_payload(
            31.4, feels_like=29.6, tz_shift=-6 * 3600
        )

        response = self.get_dashboard(TEXAS)

        self.assertContains(response, "Clear sky")
        self.assertContains(response, "Feels like")
        self.assertContains(response, "30°C")
        self.assertContains(response, "41%")  # humidity
        self.assertContains(response, "4.1 m/s")  # wind
        self.assertContains(response, "20%")  # cloud cover
        self.assertContains(response, "1016 hPa")
        # Sunrise/sunset in the location's local time (UTC-6).
        self.assertContains(response, "06:30")
        self.assertContains(response, "17:15")
        self.assertContains(response, "UV index")
        self.assertContains(response, "Not available")

    def test_missing_optional_fields_show_not_available(self):
        self.client_mock.current_weather.return_value = {"main": {"temp": 12}, "name": "Paris"}

        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "12°C")
        self.assertContains(response, "Not available")

    def test_name_falls_back_to_weather_response_when_not_given(self):
        self.client_mock.current_weather.return_value = current_payload(10, name="Montmartre")

        response = self.get_dashboard({"lat": "48.8867", "lon": "2.3431"})

        self.assertContains(response, "Montmartre")

    def test_invalid_coordinates_are_rejected_without_calling_openweather(self):
        for params in (
            {},
            {"lat": "abc", "lon": "2"},
            {"lat": "91", "lon": "2"},
            {"lat": "45", "lon": "-181"},
            {"lat": "nan", "lon": "2"},
            {"lat": "45", "lon": "2", "name": "x" * 101},
        ):
            with self.subTest(params=params):
                response = self.get_dashboard(params)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "Choose a location from the search results", status_code=400)

        self.client_mock.current_weather.assert_not_called()


class WeatherCacheTests(DashboardTestCase):
    def test_repeat_requests_within_ten_minutes_reuse_cached_weather(self):
        self.client_mock.current_weather.side_effect = [current_payload(31.4), current_payload(25.0)]

        first = self.get_dashboard(TEXAS)
        self.clock = T0 + timedelta(minutes=9, seconds=59)
        second = self.get_dashboard(TEXAS)

        self.assertEqual(self.client_mock.current_weather.call_count, 1)
        self.assertContains(first, "31°C")
        self.assertContains(second, "31°C")
        self.assertContains(second, "9 Nov 2026, 14:05 UTC")

    def test_weather_is_refreshed_once_ten_minutes_have_passed(self):
        self.client_mock.current_weather.side_effect = [current_payload(31.4), current_payload(25.0)]

        self.get_dashboard(TEXAS)
        self.clock = T0 + timedelta(minutes=10)
        response = self.get_dashboard(TEXAS)

        self.assertEqual(self.client_mock.current_weather.call_count, 2)
        self.assertContains(response, "25°C")
        self.assertContains(response, "9 Nov 2026, 14:15 UTC")

    def test_upstream_failure_shows_older_cached_weather_with_last_updated_time(self):
        self.client_mock.current_weather.side_effect = [
            current_payload(31.4),
            OpenWeatherError("Could not reach OpenWeather."),
        ]

        self.get_dashboard(TEXAS)
        self.clock = T0 + timedelta(minutes=45)
        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client_mock.current_weather.call_count, 2)
        self.assertContains(response, "31°C")
        self.assertContains(response, "couldn't reach the weather service")
        self.assertContains(response, "Last updated")
        self.assertContains(response, "9 Nov 2026, 14:05 UTC")
        self.assertContains(response, 'datetime="2026-11-09T14:05:00+00:00"')
        self.assertContains(response, "Try again")

    def test_stale_fallback_is_only_used_for_the_same_location(self):
        self.client_mock.current_weather.side_effect = [
            current_payload(31.4),
            OpenWeatherError("Could not reach OpenWeather."),
        ]

        self.get_dashboard(TEXAS)
        response = self.get_dashboard(FRANCE)

        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, "31°C", status_code=503)

    def test_upstream_failure_without_cached_weather_shows_error_and_retry(self):
        self.client_mock.current_weather.side_effect = OpenWeatherError("Could not reach OpenWeather.")

        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "couldn&#x27;t load the weather", status_code=503)
        retry_href = reverse("weather:dashboard") + "?lat=33.6618&amp;lon=-95.5555"
        self.assertContains(response, f'href="{retry_href}', status_code=503)
        self.assertContains(response, "Try again", status_code=503)
        self.assertContains(response, "Search again", status_code=503)
        self.assertNotContains(response, "°C", status_code=503)

    def test_retry_after_failure_fetches_again(self):
        self.client_mock.current_weather.side_effect = [
            OpenWeatherError("Could not reach OpenWeather."),
            current_payload(31.4),
        ]

        self.get_dashboard(TEXAS)
        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "31°C")

    def test_malformed_response_is_not_cached_and_falls_back_to_older_weather(self):
        self.client_mock.current_weather.side_effect = [
            current_payload(31.4),
            {"cod": "500"},
            current_payload(20.0),
        ]

        self.get_dashboard(TEXAS)
        self.clock = T0 + timedelta(minutes=11)
        stale = self.get_dashboard(TEXAS)
        fresh = self.get_dashboard(TEXAS)

        self.assertContains(stale, "31°C")
        self.assertContains(stale, "Last updated")
        self.assertContains(fresh, "20°C")

    def test_missing_api_key_without_cache_shows_clear_message(self):
        self.client_mock.current_weather.side_effect = MissingAPIKeyError("no key")

        response = self.get_dashboard(TEXAS)

        self.assertContains(response, "no OpenWeather API key is configured", status_code=503)


@override_settings(OPENWEATHER_API_KEY="secret-test-key")
class DashboardApiKeyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_dashboard_never_renders_api_key(self):
        with mock.patch("weather.openweather.urlopen") as urlopen:
            urlopen.side_effect = TimeoutError("timed out")
            with self.assertLogs("weather.openweather", level="WARNING") as logs:
                response = self.client.get(reverse("weather:dashboard"), TEXAS)

        urlopen.assert_called_once()
        self.assertNotContains(response, "secret-test-key", status_code=503)
        self.assertTrue(all("secret-test-key" not in line for line in logs.output))
