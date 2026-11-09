from datetime import datetime
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase

from weather import services
from weather.openweather import OpenWeatherError


class SearchLocationsTests(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch("weather.services.get_client")
        self.client_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def test_builds_labels_with_state_and_country_name(self):
        self.client_mock.geocode_city.return_value = [
            {"name": "Paris", "lat": 33.66, "lon": -95.55, "country": "US", "state": "Texas"},
        ]

        [location] = services.search_locations("Paris")

        self.assertEqual(location.label, "Paris, Texas, United States")
        self.assertEqual((location.lat, location.lon), (33.66, -95.55))

    def test_unknown_country_code_falls_back_to_code(self):
        self.client_mock.geocode_city.return_value = [
            {"name": "Testville", "lat": 1, "lon": 2, "country": "ZZ"},
        ]

        [location] = services.search_locations("Testville")

        self.assertEqual(location.label, "Testville, ZZ")

    def test_drops_duplicate_and_malformed_matches(self):
        paris = {"name": "Paris", "lat": 48.85889, "lon": 2.32004, "country": "FR", "state": "Ile-de-France"}
        self.client_mock.geocode_city.return_value = [
            paris,
            dict(paris),
            {"name": "Broken"},
        ]

        locations = services.search_locations("Paris")

        self.assertEqual([loc.label for loc in locations], ["Paris, Ile-de-France, France"])

    def test_unexpected_response_shape_raises(self):
        self.client_mock.geocode_city.return_value = {"cod": "401"}

        with self.assertRaises(OpenWeatherError):
            services.search_locations("Paris")


class CurrentWeatherServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        patcher = mock.patch("weather.services.get_client")
        self.client_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def test_coordinates_are_rounded_so_nearby_requests_share_the_cache(self):
        self.client_mock.current_weather.return_value = {"main": {"temp": 12.5}}

        first = services.get_current_weather(33.66179, -95.555513)
        second = services.get_current_weather("33.6618", "-95.5555")

        self.client_mock.current_weather.assert_called_once_with(33.6618, -95.5555)
        self.assertEqual(first, second)
        self.assertFalse(second.is_stale)

    def test_response_without_temperature_raises(self):
        for raw in ({}, [], {"main": {}}, {"main": {"temp": "warm"}}, {"main": {"temp": True}}):
            with self.subTest(raw=raw):
                with self.assertRaises(OpenWeatherError):
                    services.parse_current_weather(raw)

    def test_sunrise_and_sunset_use_the_locations_utc_offset(self):
        current = services.parse_current_weather(
            {"main": {"temp": 1}, "sys": {"sunrise": 1794227400, "sunset": 1794266100}, "timezone": 3600}
        )

        self.assertEqual(current.sunrise, datetime(2026, 11, 9, 13, 30))
        self.assertEqual(current.sunset, datetime(2026, 11, 10, 0, 15))
        self.assertIsNone(current.sunrise.tzinfo)
