from django.test import TestCase
from django.templatetags.static import static
from django.urls import reverse


class UseMyLocationTests(TestCase):
    """The browser asks for location only after the button is clicked (FR-6).

    The geolocation itself runs in static/js/current-location.js; these tests
    check the server-rendered hooks it relies on.
    """

    def setUp(self):
        self.response = self.client.get(reverse("weather:search"))

    def test_search_page_has_a_use_my_location_button(self):
        self.assertContains(
            self.response,
            '<button type="button" id="use-location" class="button button-secondary" '
            'aria-describedby="use-location-hint" hidden>Use my location</button>',
            html=True,
        )

    def test_button_knows_where_the_dashboard_is(self):
        self.assertContains(
            self.response,
            f'id="current-location" data-dashboard-url="{reverse("weather:dashboard")}"',
        )

    def test_status_messages_are_announced_politely(self):
        self.assertContains(
            self.response,
            '<p id="location-status" class="location-status" role="status" aria-live="polite"></p>',
            html=True,
        )

    def test_location_script_is_loaded_with_manual_search_still_present(self):
        self.assertContains(self.response, f'<script src="{static("js/current-location.js")}" defer></script>', html=True)
        self.assertContains(self.response, 'id="location-query"')
        self.assertContains(self.response, 'id="postal-code"')

    def test_location_script_is_served(self):
        from django.contrib.staticfiles import finders

        path = finders.find("js/current-location.js")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as script:
            source = script.read()
        # Location is requested from the click handler, not on page load.
        self.assertIn('addEventListener("click"', source)
        self.assertIn("getCurrentPosition", source)
        self.assertIn("PERMISSION_DENIED", source)
