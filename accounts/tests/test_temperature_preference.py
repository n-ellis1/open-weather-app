from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import TemperaturePreference
from accounts.templatetags.temperature import temperature
from weather.tests.test_dashboard_views import FRANCE, TEXAS, current_payload

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"
DASHBOARD_TEXAS = reverse("weather:dashboard") + "?lat=33.6618&lon=-95.5555&name=Paris&state=Texas&country=US"


class TemperatureFilterTests(SimpleTestCase):
    def test_celsius_is_rounded_and_labelled(self):
        self.assertEqual(temperature(31.4, "C"), "31°C")
        self.assertEqual(temperature(-0.4, "C"), "0°C")

    def test_fahrenheit_is_converted_then_rounded(self):
        self.assertEqual(temperature(0, "F"), "32°F")
        self.assertEqual(temperature(100, "F"), "212°F")
        self.assertEqual(temperature(-40, "F"), "-40°F")
        self.assertEqual(temperature(31.4, "F"), "89°F")  # 88.52

    def test_unknown_unit_falls_back_to_celsius(self):
        self.assertEqual(temperature(12, "K"), "12°C")
        self.assertEqual(temperature(12, ""), "12°C")

    def test_missing_value_is_not_available(self):
        self.assertEqual(temperature(None, "F"), "Not available")


class PreferenceTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        patcher = mock.patch("weather.services.get_client")
        self.client_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # 31.4 °C ≈ 88.5 °F; feels like 29.6 °C ≈ 85.3 °F.
        self.client_mock.current_weather.return_value = current_payload(31.4, feels_like=29.6)

        self.ana = User.objects.create_user("ana", password=PASSWORD)
        self.ben = User.objects.create_user("ben", password=PASSWORD)

    def set_unit(self, unit, next_url=DASHBOARD_TEXAS):
        return self.client.post(reverse("accounts:temperature_unit"), {"unit": unit, "next": next_url})

    def assertFahrenheit(self, response):
        self.assertContains(response, '<p class="temperature-now">89°F</p>', html=True)
        self.assertContains(response, "Feels like 85°F")
        self.assertContains(response, "<dd>85°F</dd>", html=True)
        # No temperature reading in the other unit (the unit buttons say "°C").
        self.assertNotRegex(response.content.decode(), r"\d°C")

    def assertCelsius(self, response):
        self.assertContains(response, '<p class="temperature-now">31°C</p>', html=True)
        self.assertContains(response, "Feels like 30°C")
        self.assertContains(response, "<dd>30°C</dd>", html=True)
        self.assertNotRegex(response.content.decode(), r"\d°F")


class DefaultUnitTests(PreferenceTestCase):
    def test_new_user_sees_celsius_and_a_unit_control(self):
        self.client.force_login(self.ana)

        response = self.client.get(DASHBOARD_TEXAS)

        self.assertCelsius(response)
        self.assertContains(response, f'action="{reverse("accounts:temperature_unit")}"')
        self.assertContains(response, 'name="unit" value="C" aria-pressed="true"')
        self.assertContains(response, 'name="unit" value="F" aria-pressed="false"')
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertFalse(TemperaturePreference.objects.exists())


class ChangeUnitTests(PreferenceTestCase):
    def test_choosing_fahrenheit_saves_it_and_returns_to_the_dashboard(self):
        self.client.force_login(self.ana)

        response = self.set_unit("F")

        self.assertRedirects(response, DASHBOARD_TEXAS, fetch_redirect_response=False)
        self.assertEqual(TemperaturePreference.objects.get(user=self.ana).unit, "F")

    def test_dashboard_shows_current_and_feels_like_in_fahrenheit(self):
        self.client.force_login(self.ana)
        self.set_unit("F")

        response = self.client.get(DASHBOARD_TEXAS)

        self.assertFahrenheit(response)
        self.assertContains(response, 'name="unit" value="F" aria-pressed="true"')

    def test_switching_back_to_celsius(self):
        self.client.force_login(self.ana)
        self.set_unit("F")
        self.set_unit("C")

        response = self.client.get(DASHBOARD_TEXAS)

        self.assertCelsius(response)
        self.assertEqual(TemperaturePreference.objects.filter(user=self.ana).count(), 1)

    def test_changing_units_reuses_cached_weather(self):
        self.client.force_login(self.ana)

        celsius = self.client.get(DASHBOARD_TEXAS)
        self.set_unit("F")
        fahrenheit = self.client.get(DASHBOARD_TEXAS)
        self.set_unit("C")
        self.client.get(DASHBOARD_TEXAS)

        self.assertCelsius(celsius)
        self.assertFahrenheit(fahrenheit)
        self.client_mock.current_weather.assert_called_once_with(33.6618, -95.5555)

    def test_cached_weather_is_shared_between_users_with_different_units(self):
        TemperaturePreference.objects.create(user=self.ana, unit="F")

        self.client.force_login(self.ana)
        ana_view = self.client.get(DASHBOARD_TEXAS)
        self.client.force_login(self.ben)
        ben_view = self.client.get(DASHBOARD_TEXAS)

        self.assertFahrenheit(ana_view)
        self.assertCelsius(ben_view)
        self.client_mock.current_weather.assert_called_once()

    def test_stale_fallback_uses_the_preferred_unit(self):
        from weather.openweather import OpenWeatherError

        TemperaturePreference.objects.create(user=self.ana, unit="F")
        self.client.force_login(self.ana)
        self.client_mock.current_weather.side_effect = [
            current_payload(31.4, feels_like=29.6),
            OpenWeatherError("down"),
        ]
        self.client.get(DASHBOARD_TEXAS)

        with mock.patch("weather.services.now") as clock:
            from datetime import timedelta

            from django.utils import timezone

            clock.return_value = timezone.now() + timedelta(minutes=30)
            response = self.client.get(DASHBOARD_TEXAS)

        self.assertContains(response, "Last updated")
        self.assertFahrenheit(response)


class PersistenceTests(PreferenceTestCase):
    def test_preference_persists_after_signing_out_and_back_in(self):
        self.client.post(reverse("accounts:login"), {"username": "ana", "password": PASSWORD})
        self.set_unit("F")
        self.client.post(reverse("accounts:logout"))

        guest_view = self.client.get(DASHBOARD_TEXAS)
        self.client.post(reverse("accounts:login"), {"username": "ana", "password": PASSWORD})
        returning_view = self.client.get(DASHBOARD_TEXAS)

        self.assertCelsius(guest_view)
        self.assertFahrenheit(returning_view)


class OwnershipTests(PreferenceTestCase):
    def test_one_users_choice_does_not_change_another_users_unit(self):
        self.client.force_login(self.ana)
        self.set_unit("F")

        self.client.force_login(self.ben)
        ben_view = self.client.get(DASHBOARD_TEXAS)

        self.assertCelsius(ben_view)
        self.assertFalse(TemperaturePreference.objects.filter(user=self.ben).exists())

    def test_changing_own_unit_leaves_other_saved_preferences_alone(self):
        TemperaturePreference.objects.create(user=self.ana, unit="F")
        self.client.force_login(self.ben)

        self.set_unit("F")
        self.set_unit("C")

        self.assertEqual(TemperaturePreference.objects.get(user=self.ana).unit, "F")
        self.assertEqual(TemperaturePreference.objects.get(user=self.ben).unit, "C")

    def test_posted_user_field_is_ignored(self):
        self.client.force_login(self.ben)

        self.client.post(
            reverse("accounts:temperature_unit"),
            {"unit": "F", "user": self.ana.pk, "user_id": self.ana.pk},
        )

        self.assertFalse(TemperaturePreference.objects.filter(user=self.ana).exists())
        self.assertEqual(TemperaturePreference.objects.get(user=self.ben).unit, "F")


class UnitEndpointProtectionTests(PreferenceTestCase):
    def test_guest_is_sent_to_sign_in_and_nothing_is_saved(self):
        response = self.set_unit("F")

        self.assertRedirects(
            response,
            reverse("accounts:login") + "?next=" + reverse("accounts:temperature_unit"),
            fetch_redirect_response=False,
        )
        self.assertFalse(TemperaturePreference.objects.exists())

    def test_get_is_not_allowed(self):
        self.client.force_login(self.ana)

        response = self.client.get(reverse("accounts:temperature_unit"), {"unit": "F"})

        self.assertEqual(response.status_code, 405)
        self.assertFalse(TemperaturePreference.objects.exists())

    def test_post_without_csrf_token_is_rejected(self):
        self.client.handler.enforce_csrf_checks = True
        self.client.force_login(self.ana)

        response = self.set_unit("F")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(TemperaturePreference.objects.exists())

    def test_invalid_unit_is_rejected_without_changing_preference(self):
        TemperaturePreference.objects.create(user=self.ana, unit="F")
        self.client.force_login(self.ana)

        for unit in ("K", "", "f", "Fahrenheit"):
            with self.subTest(unit=unit):
                response = self.set_unit(unit)
                self.assertEqual(response.status_code, 400)

        self.assertEqual(TemperaturePreference.objects.get(user=self.ana).unit, "F")

    def test_external_next_url_redirects_to_search(self):
        self.client.force_login(self.ana)

        for next_url in ("https://evil.example/", "//evil.example/", ""):
            with self.subTest(next_url=next_url):
                response = self.set_unit("F", next_url=next_url)
                self.assertRedirects(response, reverse("weather:search"))


class OtherLocationTests(PreferenceTestCase):
    def test_france_dashboard_also_uses_saved_unit(self):
        TemperaturePreference.objects.create(user=self.ana, unit="F")
        self.client.force_login(self.ana)
        self.client_mock.current_weather.return_value = current_payload(8.2, feels_like=6.0)

        response = self.client.get(reverse("weather:dashboard"), FRANCE)

        self.assertContains(response, '<p class="temperature-now">47°F</p>', html=True)  # 46.76
        self.assertContains(response, "Feels like 43°F")  # 42.8
