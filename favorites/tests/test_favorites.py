"""Favorite locations (FR-9, FR-10, FR-11). OpenWeather is always mocked."""

from html import unescape
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from favorites.models import Favorite, SavedLocation
from weather.tests.test_dashboard_views import FRANCE, TEXAS, current_payload
from weather.tests.test_search_views import PARIS_MATCHES

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"
SAVE_URL = reverse("favorites:save")
LIST_URL = reverse("favorites:list")
SEARCH_PARIS = reverse("weather:search") + "?q=Paris"


def dashboard_url(params):
    from urllib.parse import urlencode

    return reverse("weather:dashboard") + "?" + urlencode(params)


class FavoritesTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        patcher = mock.patch("weather.services.get_client")
        self.client_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.client_mock.geocode_city.return_value = PARIS_MATCHES
        self.client_mock.current_weather.return_value = current_payload(31.4)

        self.ana = User.objects.create_user("ana", password=PASSWORD)
        self.ben = User.objects.create_user("ben", password=PASSWORD)

    def save(self, params, next_url=SEARCH_PARIS):
        return self.client.post(SAVE_URL, {**params, "next": next_url})

    def add_favorite(self, user, params):
        location, _ = SavedLocation.objects.get_or_create(
            lat=params["lat"],
            lon=params["lon"],
            defaults={
                "name": params.get("name", ""),
                "state": params.get("state", ""),
                "country_code": params.get("country", ""),
            },
        )
        return Favorite.objects.create(user=user, location=location)

    def favorites_of(self, user):
        return [
            (f.location.name, f.location.state, f.location.country_code, float(f.location.lat), float(f.location.lon))
            for f in Favorite.objects.filter(user=user).select_related("location").order_by("pk")
        ]


TEXAS_ROW = ("Paris", "Texas", "US", 33.6618, -95.5555)
FRANCE_ROW = ("Paris", "Ile-de-France", "FR", 48.8589, 2.32)


class SaveFromSearchTests(FavoritesTestCase):
    def test_signed_in_search_results_each_have_a_save_form(self):
        self.client.force_login(self.ana)

        response = self.client.get(reverse("weather:search"), {"q": "Paris"})

        self.assertContains(response, f'action="{SAVE_URL}"', count=2)
        self.assertContains(response, 'name="lat" value="33.6618"')
        self.assertContains(response, 'name="lon" value="-95.5555"')
        self.assertContains(response, 'name="lat" value="48.8589"')
        self.assertContains(response, 'name="state" value="Texas"')
        self.assertContains(response, 'name="next" value="/?q=Paris"')
        self.assertContains(response, "csrfmiddlewaretoken")
        # Each button names its location for screen readers.
        self.assertContains(response, "Save <span class=\"visually-hidden\">Paris, Texas, United States to favorites</span>")

    def test_guests_see_no_save_forms_but_a_sign_in_hint(self):
        response = self.client.get(reverse("weather:search"), {"q": "Paris"})

        self.assertNotContains(response, f'action="{SAVE_URL}"')
        self.assertContains(response, "to save locations to your favorites")

    def test_saving_a_search_result_stores_it_and_returns_to_the_results(self):
        self.client.force_login(self.ana)

        response = self.save(TEXAS)

        self.assertRedirects(response, SEARCH_PARIS, fetch_redirect_response=False)
        self.assertEqual(self.favorites_of(self.ana), [TEXAS_ROW])

    def test_results_mark_locations_already_saved(self):
        self.add_favorite(self.ana, TEXAS)
        self.client.force_login(self.ana)

        response = self.client.get(reverse("weather:search"), {"q": "Paris"})

        # Only France still offers a Save button; Texas shows it is saved.
        self.assertContains(response, f'action="{SAVE_URL}"', count=1)
        self.assertContains(response, 'name="lat" value="48.8589"')
        self.assertContains(response, "Saved <span class=\"visually-hidden\">Paris, Texas, United States is in your favorites</span>")

    def test_confirmation_message_after_saving(self):
        self.client.force_login(self.ana)

        response = self.client.post(SAVE_URL, {**TEXAS, "next": SEARCH_PARIS}, follow=True)

        self.assertContains(response, "Saved Paris, Texas, United States to your favorites.")


class SaveFromDashboardTests(FavoritesTestCase):
    def test_dashboard_has_a_save_form_for_the_selected_location(self):
        self.client.force_login(self.ana)

        response = self.client.get(reverse("weather:dashboard"), TEXAS)

        self.assertContains(response, f'action="{SAVE_URL}"', count=1)
        self.assertContains(response, 'name="lat" value="33.6618"')
        self.assertContains(response, 'name="lon" value="-95.5555"')
        self.assertContains(response, 'name="name" value="Paris"')
        self.assertContains(response, "Save to favorites")

    def test_saving_from_the_dashboard_returns_there_and_shows_it_saved(self):
        self.client.force_login(self.ana)
        url = dashboard_url(TEXAS)

        response = self.save(TEXAS, next_url=url)
        self.assertRedirects(response, url, fetch_redirect_response=False)
        dashboard = self.client.get(url)

        self.assertEqual(self.favorites_of(self.ana), [TEXAS_ROW])
        self.assertNotContains(dashboard, f'action="{SAVE_URL}"')
        self.assertContains(dashboard, "In your favorites")
        self.assertContains(dashboard, f'href="{LIST_URL}"')

    def test_device_location_dashboard_saves_the_reported_place_name(self):
        self.client_mock.current_weather.return_value = current_payload(20.0, name="Mitte")
        self.client.force_login(self.ana)

        response = self.client.get(reverse("weather:dashboard"), {"lat": "52.52", "lon": "13.405"})

        self.assertContains(response, 'name="name" value="Mitte"')

    def test_dashboard_save_form_is_shown_even_when_weather_is_unavailable(self):
        from weather.openweather import OpenWeatherError

        self.client_mock.current_weather.side_effect = OpenWeatherError("down")
        self.client.force_login(self.ana)

        response = self.client.get(reverse("weather:dashboard"), FRANCE)

        self.assertContains(response, f'action="{SAVE_URL}"', count=1, status_code=503)

    def test_guests_see_a_sign_in_hint_instead(self):
        response = self.client.get(reverse("weather:dashboard"), TEXAS)

        self.assertNotContains(response, f'action="{SAVE_URL}"')
        self.assertContains(response, "to save this location to your favorites")


class DuplicateSaveTests(FavoritesTestCase):
    def test_saving_the_same_location_twice_keeps_one_entry(self):
        self.client.force_login(self.ana)

        self.save(TEXAS)
        response = self.client.post(SAVE_URL, {**TEXAS, "next": SEARCH_PARIS}, follow=True)

        self.assertEqual(self.favorites_of(self.ana), [TEXAS_ROW])
        self.assertContains(response, "Paris, Texas, United States is already in your favorites.")

    def test_same_coordinates_with_a_different_label_are_the_same_favorite(self):
        self.client.force_login(self.ana)

        self.save(TEXAS)
        self.save({"lat": "33.66181", "lon": "-95.55549"})  # rounds to the same place

        self.assertEqual(self.favorites_of(self.ana), [TEXAS_ROW])

    def test_places_with_the_same_name_are_distinguished_by_coordinates(self):
        self.client.force_login(self.ana)

        self.save(TEXAS)
        self.save(FRANCE)

        self.assertEqual(self.favorites_of(self.ana), [TEXAS_ROW, FRANCE_ROW])

    def test_two_users_saving_one_place_each_get_their_own_entry(self):
        self.client.force_login(self.ana)
        self.save(TEXAS)
        self.client.force_login(self.ben)
        self.save(TEXAS)

        self.assertEqual(self.favorites_of(self.ana), [TEXAS_ROW])
        self.assertEqual(self.favorites_of(self.ben), [TEXAS_ROW])
        self.assertEqual(SavedLocation.objects.count(), 1)

    def test_a_later_save_fills_in_a_missing_name(self):
        self.client.force_login(self.ana)
        self.save({"lat": TEXAS["lat"], "lon": TEXAS["lon"]})

        self.save(TEXAS)

        self.assertEqual(self.favorites_of(self.ana), [TEXAS_ROW])


class SaveProtectionTests(FavoritesTestCase):
    def test_guest_is_sent_to_sign_in_and_nothing_is_saved(self):
        response = self.save(TEXAS)

        self.assertRedirects(
            response, reverse("accounts:login") + "?next=" + SAVE_URL, fetch_redirect_response=False
        )
        self.assertFalse(Favorite.objects.exists())

    def test_get_is_not_allowed(self):
        self.client.force_login(self.ana)

        response = self.client.get(SAVE_URL, TEXAS)

        self.assertEqual(response.status_code, 405)
        self.assertFalse(Favorite.objects.exists())

    def test_post_without_csrf_token_is_rejected(self):
        self.client.handler.enforce_csrf_checks = True
        self.client.force_login(self.ana)

        response = self.save(TEXAS)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Favorite.objects.exists())

    def test_invalid_coordinates_are_rejected(self):
        self.client.force_login(self.ana)

        for params in ({"lat": "91", "lon": "0"}, {"lat": "x", "lon": "0"}, {"lon": "0"}, {"lat": "nan", "lon": "0"}):
            with self.subTest(params=params):
                response = self.save(params)
                self.assertEqual(response.status_code, 400)

        self.assertFalse(Favorite.objects.exists())

    def test_posted_user_field_is_ignored(self):
        self.client.force_login(self.ben)

        self.save({**TEXAS, "user": self.ana.pk, "user_id": self.ana.pk})

        self.assertEqual(self.favorites_of(self.ana), [])
        self.assertEqual(self.favorites_of(self.ben), [TEXAS_ROW])

    def test_external_next_url_redirects_to_favorites(self):
        self.client.force_login(self.ana)

        for next_url in ("https://evil.example/", "//evil.example/", ""):
            with self.subTest(next_url=next_url):
                response = self.save(TEXAS, next_url=next_url)
                self.assertRedirects(response, LIST_URL, fetch_redirect_response=False)


class FavoritesListTests(FavoritesTestCase):
    def test_header_shows_favorites_link_only_when_signed_in(self):
        guest = self.client.get(reverse("weather:search"))
        self.client.force_login(self.ana)
        signed_in = self.client.get(reverse("weather:search"))

        self.assertNotContains(guest, f'href="{LIST_URL}"')
        self.assertContains(signed_in, f'<a href="{LIST_URL}">Favorites</a>', html=True)

    def test_guest_is_sent_to_sign_in(self):
        response = self.client.get(LIST_URL)

        self.assertRedirects(response, reverse("accounts:login") + "?next=" + LIST_URL, fetch_redirect_response=False)

    def test_empty_list_points_to_search(self):
        self.client.force_login(self.ana)

        response = self.client.get(LIST_URL)

        self.assertContains(response, "You haven't saved any locations yet.")
        self.assertContains(response, f'href="{reverse("weather:search")}"')

    def test_list_shows_only_the_signed_in_users_favorites(self):
        self.add_favorite(self.ana, TEXAS)
        self.add_favorite(self.ben, FRANCE)
        self.client.force_login(self.ana)

        response = self.client.get(LIST_URL)

        self.assertContains(response, "Paris, Texas, United States")
        self.assertNotContains(response, "Ile-de-France")
        self.assertContains(response, 'class="result-item"', count=1)

    def test_list_does_not_call_openweather(self):
        self.add_favorite(self.ana, TEXAS)
        self.client.force_login(self.ana)

        self.client.get(LIST_URL)

        self.client_mock.current_weather.assert_not_called()
        self.client_mock.geocode_city.assert_not_called()


class OpenFavoriteTests(FavoritesTestCase):
    def dashboard_links(self, response):
        """Return the query params of each dashboard link on the page."""
        import re

        prefix = reverse("weather:dashboard") + "?"
        links = re.findall(r'href="([^"]+)"', response.content.decode())
        return [parse_qs(urlsplit(unescape(href)).query) for href in links if href.startswith(prefix)]

    def test_each_favorite_links_to_the_dashboard_for_its_coordinates(self):
        self.add_favorite(self.ana, TEXAS)
        self.add_favorite(self.ana, FRANCE)
        self.client.force_login(self.ana)

        links = self.dashboard_links(self.client.get(LIST_URL))

        self.assertCountEqual(
            [(q["lat"][0], q["lon"][0], q["name"][0], q["state"][0], q["country"][0]) for q in links],
            [("33.6618", "-95.5555", "Paris", "Texas", "US"), ("48.8589", "2.32", "Paris", "Ile-de-France", "FR")],
        )

    def test_opening_a_favorite_shows_weather_for_that_location(self):
        self.add_favorite(self.ana, TEXAS)
        self.add_favorite(self.ana, FRANCE)
        self.client.force_login(self.ana)
        texas = next(q for q in self.dashboard_links(self.client.get(LIST_URL)) if q["country"] == ["US"])

        response = self.client.get(reverse("weather:dashboard"), {k: v[0] for k, v in texas.items()})

        self.assertContains(response, "<h1 id=\"location-heading\">Paris, Texas, United States</h1>", html=True)
        self.client_mock.current_weather.assert_called_once_with(33.6618, -95.5555)


class RemoveFavoriteTests(FavoritesTestCase):
    def remove(self, favorite):
        return self.client.post(reverse("favorites:remove", args=[favorite.pk]))

    def test_list_has_a_remove_form_per_favorite(self):
        favorite = self.add_favorite(self.ana, TEXAS)
        self.client.force_login(self.ana)

        response = self.client.get(LIST_URL)

        self.assertContains(response, f'action="{reverse("favorites:remove", args=[favorite.pk])}"')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, "Remove <span class=\"visually-hidden\">Paris, Texas, United States from favorites</span>")

    def test_removing_a_favorite_deletes_it_and_returns_to_the_list(self):
        favorite = self.add_favorite(self.ana, TEXAS)
        keep = self.add_favorite(self.ana, FRANCE)
        self.client.force_login(self.ana)

        response = self.client.post(reverse("favorites:remove", args=[favorite.pk]), follow=True)

        self.assertRedirects(response, LIST_URL)
        self.assertEqual(list(Favorite.objects.filter(user=self.ana)), [keep])
        self.assertContains(response, "Removed Paris, Texas, United States from your favorites.")
        self.assertNotContains(response, "Texas, United States</span>")

    def test_removing_one_users_favorite_keeps_another_users_copy(self):
        favorite = self.add_favorite(self.ana, TEXAS)
        self.add_favorite(self.ben, TEXAS)
        self.client.force_login(self.ana)

        self.remove(favorite)

        self.assertEqual(self.favorites_of(self.ana), [])
        self.assertEqual(self.favorites_of(self.ben), [TEXAS_ROW])

    def test_cannot_remove_another_users_favorite(self):
        bens = self.add_favorite(self.ben, TEXAS)
        self.client.force_login(self.ana)

        response = self.remove(bens)

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Favorite.objects.filter(pk=bens.pk).exists())

    def test_unknown_id_is_not_found(self):
        self.client.force_login(self.ana)

        response = self.client.post(reverse("favorites:remove", args=[999]))

        self.assertEqual(response.status_code, 404)

    def test_guest_is_sent_to_sign_in_and_nothing_is_removed(self):
        favorite = self.add_favorite(self.ana, TEXAS)
        url = reverse("favorites:remove", args=[favorite.pk])

        response = self.client.post(url)

        self.assertRedirects(response, reverse("accounts:login") + "?next=" + url, fetch_redirect_response=False)
        self.assertTrue(Favorite.objects.filter(pk=favorite.pk).exists())

    def test_get_is_not_allowed(self):
        favorite = self.add_favorite(self.ana, TEXAS)
        self.client.force_login(self.ana)

        response = self.client.get(reverse("favorites:remove", args=[favorite.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Favorite.objects.filter(pk=favorite.pk).exists())

    def test_post_without_csrf_token_is_rejected(self):
        favorite = self.add_favorite(self.ana, TEXAS)
        self.client.handler.enforce_csrf_checks = True
        self.client.force_login(self.ana)

        response = self.remove(favorite)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Favorite.objects.filter(pk=favorite.pk).exists())

    def test_removed_favorite_can_be_saved_again(self):
        favorite = self.add_favorite(self.ana, TEXAS)
        self.client.force_login(self.ana)

        self.remove(favorite)
        self.save(TEXAS)

        self.assertEqual(self.favorites_of(self.ana), [TEXAS_ROW])
