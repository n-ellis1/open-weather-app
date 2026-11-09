# Weather App Handoff

## Current status (2026-11-09)
Milestone done: search result → current-weather dashboard (FR-7) with 10-minute cache and stale fallback (NFR-1, NFR-3). Uncommitted, awaiting review. Previous milestone (setup + city search, FR-4 city part, FR-5) is committed in `39f48ab`.

What changed:
- `weather/openweather.py`: `current_weather(lat, lon)` calls `/data/2.5/weather?units=metric` through the same key-safe `_get_json`.
- `weather/services.py`:
  - `CurrentWeather` and `WeatherReport(current, fetched_at, is_stale)` dataclasses.
  - `parse_current_weather()` requires only `main.temp` (otherwise raises `OpenWeatherError`). Other fields are `None` when missing. Sunrise and sunset are naive local times using the response's `timezone` offset.
  - `get_current_weather(lat, lon)` rounds coordinates to 4 decimals, uses cache key `weather:current:{lat}:{lon}`, and reuses an entry for less than `WEATHER_FRESH_FOR` (10 min). When a refresh fails (`OpenWeatherError`, `MissingAPIKeyError`, or a malformed payload), it returns the cached entry with `is_stale=True`. With no cached entry, it re-raises. Entries are kept for `WEATHER_KEEP_FOR` (24 h). `services.now()` is the clock that tests patch.
- `weather/views.py` `dashboard` at `/weather/?lat&lon&name&state&country`: validates the coordinate range and finiteness and the name/state length (100); otherwise it returns 400 with "Choose a location from the search results". It returns 503 with an error, "Try again" (same URL), and "Search again" when there's no data. The label comes from the query params and falls back to the response `name`, then to the coordinates.
- `weather/templates/weather/dashboard.html` (new) and the search results now link to the dashboard (lat/lon via `unlocalize`). `theme.css` gained `.result-link`, `.button-row`, `.weather-summary`, `.temperature-now`, `.detail-grid`/`.detail`.
- `config/settings.py`: explicit `CACHES` (LocMemCache, 1000 entries). README layout/run notes updated.

## Decisions
- **No UV index yet:** `/data/2.5/weather` (works with any free key) doesn't return UV, so the dashboard shows "UV index: Not available". Getting UV (FR-7) and daily highs/lows (FR-8) needs One Call 3.0 (`/data/3.0/onecall`), which requires a separate OpenWeather "One Call by Call" subscription. **Ask the user** whether to switch before building the forecast.
- Temperatures are stored in metric (°C, m/s) and rounded to whole degrees for display. FR-3 unit conversion should happen at display time.
- The cache is per process and in memory, so a restart clears the stale fallback. Switch to a database or file cache if the fallback must survive restarts.
- "Last updated" is shown in server time (UTC) with a `<time datetime>` attribute. The stale banner uses `role="status"`, and errors use `role="alert"`.
- Dark theme: reuse `static/css/theme.css` tokens and classes and extend `base.html`. The app is dark only.
- Tests patch `weather.services.get_client` and `weather.services.now`, and call `cache.clear()` in setUp.

## Verification
- TDD: the dashboard tests failed first (no service/view), then passed. The caching tests then failed as expected (`2 != 1` calls, 503 instead of stale fallback) before the cache was added.
- `uv run python manage.py test` → 39 tests, OK (offline).
- `uv run python manage.py check` → no issues. Runserver smoke test without a key: the dashboard returned 503 with the missing-key message, an invalid location returned 400, and `theme.css` returned 200.
- Not yet tested against the real OpenWeather API (no key yet).

## Next task (proposed)
- Resolve the One Call 3.0 question above, then build the multi-day forecast with an interactive chart and per-day text details (FR-8) on the dashboard, cached like current weather.
- Small follow-ups: ZIP/postal code search (FR-4, `/geo/1.0/zip`); a live check of search and the dashboard once the API key is added.
