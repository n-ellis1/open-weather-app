# Weather App Handoff

## Current status (2026-11-09)
Milestone done: Task 3, ZIP/postal-code search (FR-4) and "Use my location" (FR-6). The changes are uncommitted and awaiting review. The previous milestone (dashboard, cache, stale fallback) is committed in `6be80e1`.

What changed:
- `weather/openweather.py`: `geocode_zip(zip_code, country_code)` calls `/geo/1.0/zip?zip={code},{country}`. A new `OpenWeatherNotFoundError` (a subclass of `OpenWeatherError`) is raised on HTTP 404 by any endpoint.
- `weather/services.py`: `search_postal_code(code, country)` returns `[Location]`, or `[]` on a 404. It raises `OpenWeatherError` for a malformed payload. `Location` gained an optional `postal_code`. The zip endpoint returns no state.
- `weather/views.py` `search`: `?zip=&country=` runs a postal search; otherwise `?q=` runs a city search, which is unchanged. The postal code is trimmed, whitespace-collapsed, and uppercased. The country must be a code in `COUNTRY_NAMES`. The code allows up to 20 characters: letters, digits, spaces, and hyphens. Invalid input shows an error without calling OpenWeather. "Try again" reuses the same search via `retry_url`.
- `weather/countries.py`: `COUNTRY_CHOICES` (sorted by name) feeds the country `<select>`, which defaults to US.
- `search.html`: There are two `role="search"` forms (city, and postal + country). Both link results to the existing dashboard. A "Use my location" block carries `data-dashboard-url` and has a `role="status"` live region.
- `static/js/current-location.js` (new): The button stays `hidden` until the script runs. Clicking it calls `getCurrentPosition`. On success the browser goes to `/weather/?lat&lon` (4 decimals), and the dashboard falls back to the response's place name. Denied, unavailable, timeout, insecure-context, and unsupported cases each show a message plus "You can still search by city or postal code." The button uses `aria-disabled` while busy, which keeps focus.
- City search with a US state: `services.geocoding_query()` turns exactly two comma-separated parts whose second part is a US state name or USPS code (any case or spacing; 50 states + DC, in `weather/us_states.py`) into `City,ST,US`. For example, "Paris, Texas" and "Paris, TX" become "Paris,TX,US". Every other query is sent unchanged, including "Paris", "PAris", "Paris, France", and three-part queries. The results heading keeps what the user typed.
- `base.html` has a `{% block scripts %}`. `theme.css` gained a `[hidden]` override (needed because `.button` sets `display`), plus `.search-options`, `.postal-fields` (one column on mobile), `.current-location`, `.location-status(-error)`. README run notes are updated.

## Decisions
- **Still open: One Call 3.0.** `/data/2.5/weather` has no UV index, so the dashboard shows "Not available." UV (FR-7) and daily highs/lows (FR-8) need `/data/3.0/onecall`, which requires a separate "One Call by Call" subscription. Ask the user before building the forecast.
- A two-letter qualifier is always read as a US state when it is one. Some codes are also country codes, for example "London, CA" (California, not Canada) and "Berlin, DE" (Delaware, not Germany). Users can search the unqualified city and pick from the list instead.
- Geolocation dashboard links don't pass a name or country, so the label is the response's `name`.
- JS isn't unit-tested, to avoid adding a Node toolchain. The Django tests check the button, the data attribute, the live region, the script tag, and that the script requests location only from the click handler. Node isn't installed, so there was no `node --check`.
- Temperatures are stored in metric. FR-3 conversion should happen at display time (`floatformat:"0"` °C in `dashboard.html`).
- The cache is in-memory per process (LocMemCache), so a restart clears the stale fallback.
- The app is dark only. Reuse the `theme.css` tokens and classes and extend `base.html`. Tests patch `weather.services.get_client` and `weather.services.now`, and call `cache.clear()`.

## Verification
- TDD: the new tests first failed as expected (ImportError for `OpenWeatherNotFoundError`, and missing button/script/fields). They passed after implementation.
- City/state follow-up: the new qualified-spelling test failed first because the query was sent unchanged. It passed after `geocoding_query()` was added. The unqualified ("Paris", "PAris") and non-state qualifier tests passed throughout as regression guards.
- `uv run python manage.py test` → 61 tests, OK (offline).
- `uv run python manage.py check` → no issues. Runserver smoke test without a key: `/?zip=90210&country=US` showed the missing-key message. `country=ZZ` showed "Choose a country from the list." `current-location.js` returned 200. The coordinate-only dashboard returned 503 (no key).
- Not yet run against the real OpenWeather API, and geolocation hasn't been clicked through in a real browser.

## Next task
- Registration, sign-in, and saved temperature preferences (FR-1, FR-2, FR-3). Use Django auth (register, sign-in with an error for bad credentials, sign-out via POST). Add a per-user °C/°F preference model in SQLite. Add a POST + CSRF toggle that updates the dashboard temperatures and persists for future visits. Test first.
- Follow-ups: the One Call 3.0 decision before FR-8; a live check of city, postal, and location search once the API key is in `.env`.
