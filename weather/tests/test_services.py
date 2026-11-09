from unittest import mock

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
