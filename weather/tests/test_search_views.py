from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from weather.openweather import OpenWeatherError

# Shaped like OpenWeather Geocoding API /geo/1.0/direct responses.
PARIS_MATCHES = [
    {
        "name": "Paris",
        "local_names": {"fr": "Paris", "en": "Paris"},
        "lat": 48.8588897,
        "lon": 2.3200410217200766,
        "country": "FR",
        "state": "Ile-de-France",
    },
    {
        "name": "Paris",
        "lat": 33.6617962,
        "lon": -95.555513,
        "country": "US",
        "state": "Texas",
    },
]


class CitySearchViewTests(TestCase):
    def setUp(self):
        patcher = mock.patch("weather.services.get_client")
        self.get_client = patcher.start()
        self.addCleanup(patcher.stop)
        self.client_mock = self.get_client.return_value

    def test_search_for_paris_lists_texas_and_france_as_distinct_results(self):
        self.client_mock.geocode_city.return_value = PARIS_MATCHES

        response = self.client.get(reverse("weather:search"), {"q": "Paris"})

        self.assertEqual(response.status_code, 200)
        self.client_mock.geocode_city.assert_called_once_with("Paris")
        self.assertContains(response, 'class="result-item"', count=2)
        self.assertContains(response, "Paris, Texas, United States")
        self.assertContains(response, "Paris, Ile-de-France, France")

    def test_result_without_state_shows_city_and_country(self):
        self.client_mock.geocode_city.return_value = [
            {"name": "Singapore", "lat": 1.29, "lon": 103.85, "country": "SG"},
        ]

        response = self.client.get(reverse("weather:search"), {"q": "Singapore"})

        self.assertContains(response, "Singapore, Singapore")
        self.assertNotContains(response, "Singapore, , Singapore")

    def test_no_matches_shows_message(self):
        self.client_mock.geocode_city.return_value = []

        response = self.client.get(reverse("weather:search"), {"q": "Nowhereville"})

        self.assertContains(response, "No locations matched")
        self.assertNotContains(response, 'class="result-item"')

    def test_empty_query_shows_form_without_calling_openweather(self):
        response = self.client.get(reverse("weather:search"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<label for="location-query">City name</label>', html=True)
        self.client_mock.geocode_city.assert_not_called()

    def test_upstream_failure_shows_error_with_retry(self):
        self.client_mock.geocode_city.side_effect = OpenWeatherError("Could not reach OpenWeather.")

        response = self.client.get(reverse("weather:search"), {"q": "Paris"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "couldn&#x27;t reach the weather service")
        self.assertContains(response, "Try again")
        self.assertContains(response, 'id="location-query"')

    def test_overlong_query_is_rejected_without_calling_openweather(self):
        response = self.client.get(reverse("weather:search"), {"q": "x" * 101})

        self.assertContains(response, "100 characters or fewer")
        self.client_mock.geocode_city.assert_not_called()


@override_settings(OPENWEATHER_API_KEY="")
class MissingApiKeySearchTests(TestCase):
    def test_live_search_without_key_shows_clear_message(self):
        with mock.patch("weather.openweather.urlopen") as urlopen:
            response = self.client.get(reverse("weather:search"), {"q": "Paris"})

        urlopen.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no OpenWeather API key is configured")
        self.assertContains(response, "OPENWEATHER_API_KEY")


@override_settings(OPENWEATHER_API_KEY="secret-test-key")
class ApiKeyNotRenderedTests(TestCase):
    def test_search_page_never_renders_api_key(self):
        with mock.patch("weather.services.get_client") as get_client:
            get_client.return_value.geocode_city.return_value = PARIS_MATCHES
            response = self.client.get(reverse("weather:search"), {"q": "Paris"})

        self.assertNotContains(response, "secret-test-key")
