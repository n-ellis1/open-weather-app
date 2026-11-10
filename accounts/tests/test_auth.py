from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from weather.tests.test_dashboard_views import TEXAS, current_payload

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"


class RegistrationTests(TestCase):
    def test_register_page_has_labelled_fields(self):
        response = self.client.get(reverse("accounts:register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<label for="id_username"')
        self.assertContains(response, '<label for="id_password1"')
        self.assertContains(response, '<label for="id_password2"')
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_registering_creates_account_and_signs_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            {"username": "ana", "password1": PASSWORD, "password2": PASSWORD},
        )

        self.assertRedirects(response, reverse("weather:search"))
        user = User.objects.get(username="ana")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_registering_returns_to_a_safe_next_page(self):
        dashboard = reverse("weather:dashboard") + "?lat=1&lon=2"

        response = self.client.post(
            reverse("accounts:register"),
            {"username": "ana", "password1": PASSWORD, "password2": PASSWORD, "next": dashboard},
        )

        self.assertRedirects(response, dashboard, fetch_redirect_response=False)

    def test_registering_ignores_an_external_next_page(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "ana",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "next": "https://evil.example/",
            },
        )

        self.assertRedirects(response, reverse("weather:search"))

    def test_mismatched_passwords_show_an_error_and_create_no_account(self):
        response = self.client.post(
            reverse("accounts:register"),
            {"username": "ana", "password1": PASSWORD, "password2": PASSWORD + "x"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The two password fields didn’t match.")
        self.assertFalse(User.objects.filter(username="ana").exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_taken_username_shows_an_error(self):
        User.objects.create_user("ana", password=PASSWORD)

        response = self.client.post(
            reverse("accounts:register"),
            {"username": "ana", "password1": PASSWORD, "password2": PASSWORD},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A user with that username already exists.")
        self.assertEqual(User.objects.filter(username="ana").count(), 1)

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            reverse("accounts:register"),
            {"username": "ana", "password1": "12345678", "password2": "12345678"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This password is too common.")
        self.assertFalse(User.objects.filter(username="ana").exists())

    def test_signed_in_user_visiting_register_is_sent_to_search(self):
        user = User.objects.create_user("ana", password=PASSWORD)
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:register"))

        self.assertRedirects(response, reverse("weather:search"))


class SignInTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", password=PASSWORD)

    def test_sign_in_page_has_labelled_fields(self):
        response = self.client.get(reverse("accounts:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<label for="id_username"')
        self.assertContains(response, '<label for="id_password"')

    def test_correct_credentials_sign_in(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "ana", "password": PASSWORD}
        )

        self.assertRedirects(response, reverse("weather:search"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_sign_in_returns_to_the_next_page(self):
        dashboard = reverse("weather:dashboard") + "?lat=1&lon=2"

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "ana", "password": PASSWORD, "next": dashboard},
        )

        self.assertRedirects(response, dashboard, fetch_redirect_response=False)

    def test_wrong_password_shows_a_clear_error(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "ana", "password": "wrong-password"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, "Please enter a correct username and password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_username_shows_the_same_error(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "nobody", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct username and password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sign_in_rejects_post_without_csrf_token(self):
        self.client.handler.enforce_csrf_checks = True

        response = self.client.post(
            reverse("accounts:login"), {"username": "ana", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, 403)


class SignOutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", password=PASSWORD)
        self.client.force_login(self.user)

    def test_sign_out_requires_post(self):
        response = self.client.get(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_post_signs_out_and_returns_to_search(self):
        response = self.client.post(reverse("accounts:logout"))

        self.assertRedirects(response, reverse("weather:search"))
        self.assertNotIn("_auth_user_id", self.client.session)


class HeaderNavigationTests(TestCase):
    def test_guest_sees_sign_in_and_register_links(self):
        response = self.client.get(reverse("weather:search"))

        self.assertContains(response, f'href="{reverse("accounts:login")}?next=/"')
        self.assertContains(response, f'href="{reverse("accounts:register")}?next=/"')
        self.assertNotContains(response, "Sign out")

    def test_signed_in_user_sees_name_and_sign_out_form(self):
        user = User.objects.create_user("ana", password=PASSWORD)
        self.client.force_login(user)

        response = self.client.get(reverse("weather:search"))

        self.assertContains(response, "Signed in as <strong>ana</strong>")
        self.assertContains(response, f'action="{reverse("accounts:logout")}"')
        self.assertContains(response, "Sign out")
        self.assertNotContains(response, f'href="{reverse("accounts:login")}')


class GuestAccessTests(TestCase):
    """Search and the dashboard stay open to visitors who aren't signed in."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        patcher = mock.patch("weather.services.get_client")
        self.client_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def test_guest_can_search_by_city_and_postal_code(self):
        self.client_mock.geocode_city.return_value = []
        self.client_mock.geocode_zip.side_effect = None
        self.client_mock.geocode_zip.return_value = {
            "zip": "90210", "name": "Beverly Hills", "lat": 34.09, "lon": -118.41, "country": "US",
        }

        city = self.client.get(reverse("weather:search"), {"q": "Paris"})
        postal = self.client.get(reverse("weather:search"), {"zip": "90210", "country": "US"})

        self.assertEqual(city.status_code, 200)
        self.assertEqual(postal.status_code, 200)
        self.assertContains(postal, "Beverly Hills")

    def test_guest_can_view_dashboard_in_celsius(self):
        self.client_mock.current_weather.return_value = current_payload(31.4, feels_like=29.6)

        response = self.client.get(reverse("weather:dashboard"), TEXAS)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "31°C")
        self.assertContains(response, "Feels like 30°C")
        self.assertContains(response, "Sign in")
        self.assertNotContains(response, 'name="unit"')
