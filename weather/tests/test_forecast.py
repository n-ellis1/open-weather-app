"""Multi-day forecast (FR-8) and weather map (FR-12). OpenWeather is always mocked."""

from datetime import date, datetime, timedelta, timezone
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import set_temperature_unit
from weather import services
from weather.openweather import MissingAPIKeyError, OpenWeatherError

from .test_dashboard_views import T0, TEXAS, DashboardTestCase, current_payload

User = get_user_model()
CST = -6 * 3600


def sample(utc, temp, *, temp_min=None, temp_max=None, description="clear sky"):
    """One 3-hour step, shaped like an item of /data/2.5/forecast's "list"."""
    return {
        "dt": int(utc.timestamp()),
        "main": {
            "temp": temp,
            "temp_min": temp if temp_min is None else temp_min,
            "temp_max": temp if temp_max is None else temp_max,
            "humidity": 50,
        },
        "weather": [{"id": 800, "main": "Clear", "description": description, "icon": "01d"}],
        "pop": 0,
        "dt_txt": utc.strftime("%Y-%m-%d %H:%M:%S"),
    }


def forecast_payload(samples, tz_shift=CST, name="Paris"):
    return {
        "cod": "200",
        "cnt": len(samples),
        "list": samples,
        "city": {"name": name, "country": "US", "timezone": tz_shift},
    }


def utc(day, hour):
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


# In Paris, Texas (UTC-6) these samples fall on three local dates:
# 8 Nov 21:00 (1 sample), all of 9 Nov (8 samples), and 10 Nov 00:00-03:00 (2 samples).
NINE_NOV_TEMPS = [10, 12, 15, 20, 22, 19, 14, 11]
TEXAS_SAMPLES = (
    [sample(utc(9, 3), 18, description="few clouds")]
    + [
        sample(
            utc(9, 6) + timedelta(hours=3 * i),
            temp,
            temp_max=23.5 if temp == 22 else None,
            temp_min=9.2 if temp == 10 else None,
            description="light rain" if i < 5 else "clear sky",
        )
        for i, temp in enumerate(NINE_NOV_TEMPS)
    ]
    + [sample(utc(10, 6), 8, description="overcast clouds"), sample(utc(10, 9), 7, description="overcast clouds")]
)


class ParseForecastTests(SimpleTestCase):
    def test_samples_are_grouped_by_the_locations_local_date(self):
        days = services.parse_forecast(forecast_payload(TEXAS_SAMPLES))

        self.assertEqual([day.date for day in days], [date(2026, 11, 8), date(2026, 11, 9), date(2026, 11, 10)])
        self.assertEqual([day.sample_count for day in days], [1, 8, 2])

    def test_non_hour_offsets_shift_samples_into_the_next_local_day(self):
        # 21:00 UTC is 02:30 the next day in India (UTC+5:30).
        days = services.parse_forecast(
            forecast_payload([sample(utc(8, 18), 20), sample(utc(8, 21), 19)], tz_shift=19800)
        )

        self.assertEqual([(day.date, day.sample_count) for day in days], [(date(2026, 11, 8), 1), (date(2026, 11, 9), 1)])

    def test_daily_high_and_low_are_estimated_from_the_days_samples(self):
        days = services.parse_forecast(forecast_payload(TEXAS_SAMPLES))

        self.assertEqual((days[0].high, days[0].low), (18, 18))
        # Uses each sample's temp_max/temp_min, not just temp.
        self.assertEqual((days[1].high, days[1].low), (23.5, 9.2))
        self.assertEqual((days[2].high, days[2].low), (8, 7))

    def test_days_with_fewer_than_eight_samples_are_partial(self):
        days = services.parse_forecast(forecast_payload(TEXAS_SAMPLES))

        self.assertEqual([day.is_partial for day in days], [True, False, True])

    def test_conditions_are_the_days_most_common_description(self):
        days = services.parse_forecast(forecast_payload(TEXAS_SAMPLES))

        self.assertEqual([day.description for day in days], ["Few clouds", "Light rain", "Overcast clouds"])

    def test_samples_without_a_usable_temperature_are_skipped(self):
        broken = sample(utc(9, 6), 0)
        broken["main"]["temp"] = None
        broken["main"].pop("temp_min")
        broken["main"].pop("temp_max")

        days = services.parse_forecast(forecast_payload([broken, sample(utc(9, 9), 5), {"dt": "x"}]))

        self.assertEqual([(day.sample_count, day.high) for day in days], [(1, 5)])

    def test_unusable_responses_raise_openweather_error(self):
        for raw in (None, [], {"cod": "500"}, {"list": "nope"}, {"list": []}, {"list": [{"dt": 1}]}):
            with self.subTest(raw=raw), self.assertRaises(OpenWeatherError):
                services.parse_forecast(raw)


class ForecastCacheTests(SimpleTestCase):
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

    def test_forecast_is_reused_for_ten_minutes_then_refreshed(self):
        self.client_mock.forecast.return_value = forecast_payload(TEXAS_SAMPLES)

        first = services.get_forecast(33.6618, -95.5555)
        self.clock = T0 + timedelta(minutes=9, seconds=59)
        cached = services.get_forecast(33.66181, -95.55549)  # rounds to the same place
        self.assertEqual(self.client_mock.forecast.call_count, 1)
        self.assertEqual(cached, first)

        self.clock = T0 + timedelta(minutes=10)
        refreshed = services.get_forecast(33.6618, -95.5555)
        self.assertEqual(self.client_mock.forecast.call_count, 2)
        self.assertEqual(refreshed.fetched_at, self.clock)
        self.client_mock.forecast.assert_called_with(33.6618, -95.5555)

    def test_failed_refresh_returns_older_forecast_marked_stale(self):
        self.client_mock.forecast.side_effect = [
            forecast_payload(TEXAS_SAMPLES),
            OpenWeatherError("Could not reach OpenWeather."),
        ]

        services.get_forecast(33.6618, -95.5555)
        self.clock = T0 + timedelta(hours=2)
        report = services.get_forecast(33.6618, -95.5555)

        self.assertTrue(report.is_stale)
        self.assertEqual(report.fetched_at, T0)
        self.assertEqual(len(report.days), 3)

    def test_failure_without_cached_forecast_raises(self):
        self.client_mock.forecast.side_effect = OpenWeatherError("Could not reach OpenWeather.")

        with self.assertRaises(OpenWeatherError):
            services.get_forecast(33.6618, -95.5555)

    def test_forecast_and_current_weather_are_cached_separately(self):
        self.client_mock.current_weather.return_value = current_payload(31.4)
        self.client_mock.forecast.return_value = forecast_payload(TEXAS_SAMPLES)

        services.get_current_weather(33.6618, -95.5555)
        services.get_forecast(33.6618, -95.5555)

        self.assertEqual(self.client_mock.current_weather.call_count, 1)
        self.assertEqual(self.client_mock.forecast.call_count, 1)


class DashboardForecastTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.client_mock.current_weather.return_value = current_payload(31.4)
        self.client_mock.forecast.return_value = forecast_payload(TEXAS_SAMPLES)

    def test_dashboard_lists_each_local_day_with_estimated_high_low_and_conditions(self):
        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 200)
        self.client_mock.forecast.assert_called_once_with(33.6618, -95.5555)
        self.assertContains(response, "5-day forecast")
        for label in ("Sun 8 Nov", "Mon 9 Nov", "Tue 10 Nov"):
            self.assertContains(response, label)
        self.assertContains(response, "Monday 9 November")
        self.assertContains(response, "High 24°C")  # 23.5
        self.assertContains(response, "Low 9°C")
        self.assertContains(response, "Light rain")
        self.assertContains(response, "estimated from 3-hour forecasts")

    def test_partial_days_are_labelled(self):
        response = self.get_dashboard(TEXAS)

        self.assertContains(response, "Partial day", count=2)
        self.assertContains(response, "1 of 8 forecast times")
        self.assertContains(response, "2 of 8 forecast times")

    def test_chart_data_is_embedded_for_the_interactive_chart(self):
        response = self.get_dashboard(TEXAS)

        self.assertContains(response, 'id="forecast-data"')
        self.assertContains(response, 'role="tablist"')
        chart = response.context["forecast_chart"]
        self.assertEqual(chart["unit"], "C")
        self.assertEqual(
            chart["days"][1],
            {"label": "Mon 9 Nov", "high": 23.5, "low": 9.2, "description": "Light rain", "partial": False},
        )

    def test_signed_in_fahrenheit_users_see_converted_forecast(self):
        user = User.objects.create_user("ana", password="correct-horse-battery-staple")
        set_temperature_unit(user, "F")
        self.client.force_login(user)

        response = self.get_dashboard(TEXAS)

        self.assertContains(response, "High 74°F")  # 23.5 °C = 74.3 °F
        self.assertContains(response, "Low 49°F")  # 9.2 °C = 48.56 °F
        self.assertNotContains(response, "High 24°C")
        chart = response.context["forecast_chart"]
        self.assertEqual(chart["unit"], "F")
        self.assertEqual((chart["days"][1]["high"], chart["days"][1]["low"]), (74.3, 48.6))
        # Cached forecast stays metric; switching units costs no extra call.
        self.assertEqual(self.client_mock.forecast.call_count, 1)

    def test_forecast_failure_keeps_current_weather_usable(self):
        self.client_mock.forecast.side_effect = OpenWeatherError("Could not reach OpenWeather.")

        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "31°C")
        self.assertContains(response, "Clear sky")
        self.assertContains(response, "forecast is unavailable")
        self.assertContains(response, "Try again")
        self.assertNotContains(response, 'role="tablist"')

    def test_malformed_forecast_keeps_current_weather_usable(self):
        self.client_mock.forecast.return_value = {"cod": "500"}

        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "31°C")
        self.assertContains(response, "forecast is unavailable")

    def test_stale_forecast_shows_its_last_updated_time(self):
        self.client_mock.forecast.side_effect = [
            forecast_payload(TEXAS_SAMPLES),
            OpenWeatherError("Could not reach OpenWeather."),
        ]
        self.get_dashboard(TEXAS)
        self.clock = T0 + timedelta(minutes=30)

        response = self.get_dashboard(TEXAS)

        self.assertContains(response, "Mon 9 Nov")
        self.assertContains(response, "Forecast last updated")
        self.assertContains(response, "9 Nov 2026, 14:05 UTC")

    def test_forecast_is_not_requested_when_current_weather_fails(self):
        self.client_mock.current_weather.side_effect = OpenWeatherError("Could not reach OpenWeather.")

        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 503)
        self.client_mock.forecast.assert_not_called()

    def test_forecast_card_says_unavailable_when_the_request_was_skipped(self):
        self.client_mock.current_weather.side_effect = OpenWeatherError("Could not reach OpenWeather.")

        response = self.get_dashboard(TEXAS)

        self.assertContains(response, "5-day forecast", status_code=503)
        self.assertContains(response, "Forecast unavailable", status_code=503)
        self.assertNotContains(response, 'role="tablist"', status_code=503)
        self.assertNotContains(response, 'id="forecast-data"', status_code=503)

    def test_forecast_card_says_unavailable_when_the_forecast_fails(self):
        self.client_mock.forecast.side_effect = OpenWeatherError("Could not reach OpenWeather.")

        response = self.get_dashboard(TEXAS)

        self.assertContains(response, "5-day forecast")
        self.assertContains(response, "Forecast unavailable")

    def test_forecast_card_says_unavailable_without_an_api_key(self):
        self.client_mock.current_weather.side_effect = MissingAPIKeyError("no key")

        response = self.get_dashboard(TEXAS)

        self.assertContains(response, "Forecast unavailable", status_code=503)
        self.client_mock.forecast.assert_not_called()

    def test_available_forecast_does_not_say_unavailable(self):
        response = self.get_dashboard(TEXAS)

        self.assertNotContains(response, "Forecast unavailable")
        self.assertContains(response, 'role="tablist"')

    def test_missing_api_key_for_forecast_does_not_break_dashboard(self):
        self.client_mock.forecast.side_effect = MissingAPIKeyError("no key")

        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "forecast is unavailable")


class DashboardMapTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.client_mock.current_weather.return_value = current_payload(31.4)
        self.client_mock.forecast.return_value = forecast_payload(TEXAS_SAMPLES)

    def test_map_is_centered_on_selected_location_with_marker_details(self):
        response = self.get_dashboard(TEXAS)

        self.assertContains(response, 'id="weather-map"')
        self.assertContains(response, 'id="map-data"')
        self.assertEqual(
            response.context["map_data"],
            {"lat": 33.6618, "lon": -95.5555, "name": "Paris, Texas, United States", "conditions": "Clear sky, 31°C"},
        )

    def test_map_uses_leaflet_with_integrity_and_tile_attribution(self):
        response = self.get_dashboard(TEXAS)

        self.assertContains(response, "leaflet@1.9.4/dist/leaflet.js")
        self.assertContains(response, "leaflet@1.9.4/dist/leaflet.css")
        self.assertContains(response, 'integrity="sha256-', count=2)
        self.assertContains(response, "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertContains(response, "openstreetmap.org/copyright")
        self.assertContains(response, "static/js/weather-map.js")

    def test_map_conditions_use_the_viewers_unit(self):
        user = User.objects.create_user("ana", password="correct-horse-battery-staple")
        set_temperature_unit(user, "F")
        self.client.force_login(user)

        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.context["map_data"]["conditions"], "Clear sky, 89°F")

    def test_map_still_shows_location_when_weather_is_unavailable(self):
        self.client_mock.current_weather.side_effect = OpenWeatherError("Could not reach OpenWeather.")

        response = self.get_dashboard(TEXAS)

        self.assertContains(response, 'id="weather-map"', status_code=503)
        self.assertEqual(response.context["map_data"]["conditions"], "")
        self.assertEqual(response.context["map_data"]["lat"], 33.6618)

    def test_tile_fallback_message_is_rendered_hidden_with_attribution_kept(self):
        response = self.get_dashboard(TEXAS)

        self.assertContains(response, 'class="map-tile-error alert alert-warning" role="status" hidden')
        self.assertContains(response, "Map tiles couldn")
        self.assertContains(response, "OpenStreetMap</a> contributors")

    def test_site_wide_referrer_policy_is_unchanged(self):
        # The tile layer opts in to sending its origin; other pages keep same-origin.
        response = self.get_dashboard(TEXAS)

        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")

    def test_map_script_sends_origin_referer_on_tile_requests_and_handles_tile_errors(self):
        # OSM's tile usage policy requires a valid Referer; Django's same-origin
        # policy would strip it from cross-origin tile requests.
        script = (settings.BASE_DIR / "static" / "js" / "weather-map.js").read_text(encoding="utf-8")

        self.assertIn('referrerPolicy: "strict-origin-when-cross-origin"', script)
        self.assertIn('"tileerror"', script)

    def test_map_exposes_dashboard_url_for_previewed_pins(self):
        response = self.get_dashboard(TEXAS)

        self.assertContains(response, f'data-dashboard-url="{reverse("weather:dashboard")}"')
        self.assertContains(response, "Click a point on the map")

    def test_map_help_keeps_search_available_for_keyboard_users(self):
        response = self.get_dashboard(TEXAS)

        self.assertContains(
            response,
            f'<a href="{reverse("weather:search")}">search by city or ZIP/postal code</a>',
        )

    def test_rendering_the_map_requests_weather_only_for_the_selected_location(self):
        self.get_dashboard(TEXAS)

        self.client_mock.current_weather.assert_called_once_with(33.6618, -95.5555)
        self.client_mock.forecast.assert_called_once_with(33.6618, -95.5555)

    def test_view_weather_here_link_opens_dashboard_for_previewed_coordinates(self):
        # The link the preview builds: 4-decimal coordinates and no name.
        response = self.get_dashboard({"lat": "34.0522", "lon": "-118.2437"})

        self.assertEqual(response.status_code, 200)
        self.client_mock.current_weather.assert_called_once_with(34.0522, -118.2437)

    def test_map_script_previews_pins_without_requesting_weather(self):
        script = (settings.BASE_DIR / "static" / "js" / "weather-map.js").read_text(encoding="utf-8")

        self.assertIn("View weather here", script)
        # Single clicks wait so a double-click zoom can cancel the pin.
        self.assertIn('"dblclick"', script)
        self.assertIn("clearTimeout(pendingPin)", script)
        # The preview doesn't bubble clicks to the map, and nothing fetches weather.
        self.assertIn("bubblingMouseEvents: false", script)
        self.assertNotIn("fetch(", script)
        self.assertNotIn("XMLHttpRequest", script)

    @override_settings(OPENWEATHER_API_KEY="secret-test-key")
    def test_api_key_never_reaches_the_page(self):
        response = self.get_dashboard(TEXAS)

        self.assertNotContains(response, "secret-test-key")
        self.assertNotContains(response, "openweathermap.org")
