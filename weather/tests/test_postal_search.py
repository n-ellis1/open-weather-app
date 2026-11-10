from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from weather import services
from weather.openweather import OpenWeatherError, OpenWeatherNotFoundError

from .test_search_views import PARIS_MATCHES

# Shaped like an OpenWeather Geocoding API /geo/1.0/zip response.
BEVERLY_HILLS = {
    "zip": "90210",
    "name": "Beverly Hills",
    "lat": 34.0901,
    "lon": -118.4065,
    "country": "US",
}


class PostalSearchServiceTests(TestCase):
    def setUp(self):
        patcher = mock.patch("weather.services.get_client")
        self.client_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def test_returns_the_matching_location(self):
        self.client_mock.geocode_zip.return_value = BEVERLY_HILLS

        results = services.search_postal_code("90210", "US")

        self.client_mock.geocode_zip.assert_called_once_with("90210", "US")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].label, "Beverly Hills, United States")
        self.assertEqual((results[0].lat, results[0].lon), (34.0901, -118.4065))
        self.assertEqual(results[0].postal_code, "90210")

    def test_unknown_postal_code_returns_no_results(self):
        self.client_mock.geocode_zip.side_effect = OpenWeatherNotFoundError("not found")

        self.assertEqual(services.search_postal_code("00000", "US"), [])

    def test_unexpected_response_shape_raises(self):
        for payload in ([BEVERLY_HILLS], {"name": "No coordinates"}, None):
            with self.subTest(payload=payload):
                self.client_mock.geocode_zip.return_value = payload
                with self.assertRaises(OpenWeatherError):
                    services.search_postal_code("90210", "US")


class PostalSearchViewTests(TestCase):
    def setUp(self):
        patcher = mock.patch("weather.services.get_client")
        self.client_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def search(self, **params):
        return self.client.get(reverse("weather:search"), params)

    def test_search_page_offers_postal_code_and_country_fields(self):
        response = self.search()

        self.assertContains(response, '<label for="postal-code">ZIP or postal code</label>', html=True)
        self.assertContains(response, '<label for="postal-country">Country</label>', html=True)
        self.assertContains(response, '<option value="US" selected>United States</option>', html=True)
        self.assertContains(response, '<option value="GB">United Kingdom</option>', html=True)

    def test_postal_search_links_the_match_to_the_dashboard(self):
        self.client_mock.geocode_zip.return_value = BEVERLY_HILLS

        response = self.search(zip="90210", country="US")

        self.assertEqual(response.status_code, 200)
        self.client_mock.geocode_zip.assert_called_once_with("90210", "US")
        self.client_mock.geocode_city.assert_not_called()
        self.assertContains(response, 'class="result-item"', count=1)
        self.assertContains(response, "Beverly Hills, United States")
        self.assertContains(response, "Postal code 90210")
        dashboard = reverse("weather:dashboard")
        self.assertContains(
            response,
            f'href="{dashboard}?lat=34.0901&amp;lon=-118.4065&amp;name=Beverly%20Hills&amp;state=&amp;country=US"',
        )

    def test_postal_code_is_normalized_and_selected_country_is_kept(self):
        self.client_mock.geocode_zip.return_value = {
            "zip": "E14", "name": "London", "lat": 51.5074, "lon": -0.0174, "country": "GB",
        }

        response = self.search(zip="  e14 ", country="gb")

        self.client_mock.geocode_zip.assert_called_once_with("E14", "GB")
        self.assertContains(response, 'value="E14"')
        self.assertContains(response, '<option value="GB" selected>United Kingdom</option>', html=True)
        self.assertContains(response, "London, United Kingdom")

    def test_unknown_postal_code_shows_no_matches_message(self):
        self.client_mock.geocode_zip.side_effect = OpenWeatherNotFoundError("not found")

        response = self.search(zip="00000", country="US")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No locations matched postal code 00000 in United States")
        self.assertNotContains(response, 'class="result-item"')

    def test_invalid_input_is_rejected_without_calling_openweather(self):
        cases = [
            ({"zip": "90210", "country": "ZZ"}, "Choose a country from the list"),
            ({"zip": "90210", "country": ""}, "Choose a country from the list"),
            ({"zip": "9" * 21, "country": "US"}, "20 characters or fewer"),
            ({"zip": "902<10>", "country": "US"}, "letters, numbers, spaces, and hyphens"),
        ]
        for params, message in cases:
            with self.subTest(params=params):
                response = self.search(**params)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
        self.client_mock.geocode_zip.assert_not_called()

    def test_upstream_failure_shows_error_with_retry_for_the_same_postal_search(self):
        self.client_mock.geocode_zip.side_effect = OpenWeatherError("Could not reach OpenWeather.")

        response = self.search(zip="90210", country="US")

        self.assertContains(response, "couldn&#x27;t reach the weather service")
        self.assertContains(response, f'href="{reverse("weather:search")}?zip=90210&amp;country=US"')
        # Both search forms stay available.
        self.assertContains(response, 'id="location-query"')
        self.assertContains(response, 'id="postal-code"')

    def test_city_search_still_lists_multiple_matches(self):
        self.client_mock.geocode_city.return_value = PARIS_MATCHES

        response = self.search(q="Paris")

        self.client_mock.geocode_zip.assert_not_called()
        self.assertContains(response, 'class="result-item"', count=2)
        self.assertContains(response, "Paris, Texas, United States")
        self.assertContains(response, "Paris, Ile-de-France, France")


@override_settings(OPENWEATHER_API_KEY="")
class MissingApiKeyPostalSearchTests(TestCase):
    def test_postal_search_without_key_shows_clear_message(self):
        with mock.patch("weather.openweather.urlopen") as urlopen:
            response = self.client.get(reverse("weather:search"), {"zip": "90210", "country": "US"})

        urlopen.assert_not_called()
        self.assertContains(response, "no OpenWeather API key is configured")
