import io
import json
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase

from weather.openweather import MissingAPIKeyError, OpenWeatherClient, OpenWeatherError


def fake_response(payload):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return io.BytesIO(body)


class OpenWeatherClientTests(SimpleTestCase):
    def test_geocode_city_requests_direct_geocoding_with_timeout(self):
        opener = mock.Mock(return_value=fake_response([{"name": "Paris"}]))
        client = OpenWeatherClient(api_key="test-key", timeout=3, opener=opener)

        result = client.geocode_city("Paris")

        self.assertEqual(result, [{"name": "Paris"}])
        url = opener.call_args.args[0]
        parts = urlsplit(url)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.netloc, "api.openweathermap.org")
        self.assertEqual(parts.path, "/geo/1.0/direct")
        self.assertEqual(
            parse_qs(parts.query),
            {"q": ["Paris"], "limit": ["5"], "appid": ["test-key"]},
        )
        self.assertEqual(opener.call_args.kwargs, {"timeout": 3})

    def test_current_weather_requests_metric_weather_for_coordinates(self):
        opener = mock.Mock(return_value=fake_response({"main": {"temp": 12}}))
        client = OpenWeatherClient(api_key="test-key", timeout=3, opener=opener)

        result = client.current_weather(33.6618, -95.5555)

        self.assertEqual(result, {"main": {"temp": 12}})
        parts = urlsplit(opener.call_args.args[0])
        self.assertEqual(parts.netloc, "api.openweathermap.org")
        self.assertEqual(parts.path, "/data/2.5/weather")
        self.assertEqual(
            parse_qs(parts.query),
            {"lat": ["33.6618"], "lon": ["-95.5555"], "units": ["metric"], "appid": ["test-key"]},
        )
        self.assertEqual(opener.call_args.kwargs, {"timeout": 3})

    def test_current_weather_without_key_makes_no_request(self):
        opener = mock.Mock()
        client = OpenWeatherClient(api_key="", opener=opener)

        with self.assertRaises(MissingAPIKeyError):
            client.current_weather(1, 2)
        opener.assert_not_called()

    def test_missing_key_raises_without_making_a_request(self):
        opener = mock.Mock()
        client = OpenWeatherClient(api_key="", opener=opener)

        with self.assertRaises(MissingAPIKeyError):
            client.geocode_city("Paris")
        opener.assert_not_called()

    def test_http_error_raises_without_leaking_key(self):
        def opener(url, timeout):
            raise HTTPError(url, 401, "Unauthorized", {}, None)

        client = OpenWeatherClient(api_key="super-secret", opener=opener)

        with self.assertLogs("weather.openweather", level="WARNING") as logs:
            with self.assertRaises(OpenWeatherError) as caught:
                client.geocode_city("Paris")

        self.assertNotIn("super-secret", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(all("super-secret" not in line for line in logs.output))

    def test_timeout_raises_openweather_error(self):
        opener = mock.Mock(side_effect=TimeoutError("timed out"))
        client = OpenWeatherClient(api_key="k", opener=opener)

        with self.assertLogs("weather.openweather", level="WARNING"):
            with self.assertRaises(OpenWeatherError):
                client.geocode_city("Paris")

    def test_network_error_raises_openweather_error(self):
        opener = mock.Mock(side_effect=URLError("no route"))
        client = OpenWeatherClient(api_key="k", opener=opener)

        with self.assertLogs("weather.openweather", level="WARNING"):
            with self.assertRaises(OpenWeatherError):
                client.geocode_city("Paris")

    def test_invalid_json_raises_openweather_error(self):
        opener = mock.Mock(return_value=fake_response(b"not json"))
        client = OpenWeatherClient(api_key="k", opener=opener)

        with self.assertLogs("weather.openweather", level="WARNING"):
            with self.assertRaises(OpenWeatherError):
                client.geocode_city("Paris")
