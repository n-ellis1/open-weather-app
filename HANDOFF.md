# Weather App Handoff

## Current status (2026-11-09)
Milestone done: Task 6, interactive forecast (FR-8) and map (FR-12). The changes are uncommitted and awaiting review. Task 5 (favorites) is committed in `8cad647`.

What changed:
- `weather/openweather.py`: `OpenWeatherClient.forecast(lat, lon)` calls the free `/data/2.5/forecast` (5 days in 3-hour steps, metric). One Call isn't used.
- `weather/services.py`:
  - `_cached_report(kind, lat, lon, load)` is the shared cache policy (10 minutes fresh, stale fallback kept for 24 h). `get_current_weather` now uses it too, with an unchanged cache key (`weather:current:…`). Forecasts use `weather:forecast:…`.
  - `parse_forecast(raw)` groups samples by local date (UTC `dt` + `city.timezone`). Each day's high is the max `temp_max` and its low the min `temp_min` (falling back to `temp`), and its conditions are the most common description. Bad samples are skipped, and no usable samples raises `OpenWeatherError`. A `DailyForecast` is partial when it has fewer than 8 samples.
  - `get_forecast(lat, lon)` returns a `ForecastReport(days, fetched_at, is_stale)`.
- `accounts/templatetags/temperature.py`: new `convert_temperature(celsius, unit)`, also used by the `temperature` filter.
- `weather/views.py`: the dashboard requests the forecast only after current weather (fresh or stale) loads. Forecast errors, including a missing key, set `forecast_error` and the page still returns 200. Context: `forecast`, `forecast_chart` (numbers already in the viewer's unit for JS) and `map_data` (lat, lon, name, "Clear sky, 31°C" or "").
- `dashboard.html`:
  - The "5-day forecast" card has a server-rendered text panel per day (heading, High/Low, conditions, "Partial day: estimated from N of 8 forecast times"). Without JS, every panel shows.
  - The chart, legend, and day tablist are `hidden` until JS turns them on.
  - The Map card is followed by `json_script` data.
  - Leaflet CSS/JS come from unpkg with SRI (hashes checked against the CDN files) and load only on valid dashboards.
- `base.html`: new `{% block head %}`.
- `static/js/forecast-chart.js`:
  - Draws an SVG chart: a solid orange line for highs and a dashed blue line for lows, using the dataviz reference palette's validated dark pair. The palette validator wasn't run because Node isn't installed.
  - Selected-day labels and a hover tooltip.
  - Days can be selected by clicking a column, or through an ARIA tablist with arrow/Home/End keys that switches the text panel.
- `static/js/weather-map.js`:
  - Leaflet map at zoom 10 on the coordinates, with OSM tiles and "© OpenStreetMap contributors" attribution (from `data-` attributes).
  - A keyboard-focusable marker whose popup is built with `textContent`.
  - The scroll wheel zooms only after the map is focused or clicked.
- **Tile 403 fix (after the first browser check):** Edge showed OSM "Access blocked" tiles on 127.0.0.1.
  - Cause: Django's default `SECURE_REFERRER_POLICY = "same-origin"` strips the Referer from cross-origin tile requests. OSM's tile policy requires a valid Referer and forbids a restrictive Referrer-Policy.
  - Fix, scoped to the map: the Leaflet tile layer now sets `referrerPolicy: "strict-origin-when-cross-origin"`, so tiles send only the origin. The site-wide header is unchanged, and a test pins it.
  - A hidden `.map-tile-error` notice appears on Leaflet `tileerror` and hides after a batch loads cleanly.
  - OSM's "Access blocked" tiles arrive as normal images, so that case can't be detected in JS.
- **Dashboard follow-ups (while the key activates):**
  - The "5-day forecast" card is now always shown on valid dashboards. Without forecast data it shows a "Forecast unavailable." alert with Try again: either the forecast error, or "loads once current weather is available" when the request was skipped. The chart and day panels are unchanged when data exists. The forecast is still skipped when current weather fails with no cache.
  - Map pin preview in `weather-map.js`: a click on empty map waits 300 ms (a `dblclick` cancels it), then drops a yellow `circleMarker` (`bubblingMouseEvents: false`). Its popup shows the coordinates and a "View weather here" link to `data-dashboard-url?lat=…&lon=…` (4 decimals, longitude wrapped). There's no fetch/XHR; weather loads only when the user follows the link. Leaflet ignores clicks after a drag, and clicks on the existing marker, popups, and controls don't reach the map. The map help text now links to city/ZIP search for keyboard users.
- `theme.css`: chart/tab/map/Leaflet dark styles and the `--color-chart-high/low` tokens. README and AGENTS.md now list the Leaflet/OSM stack.

## Decisions
- The forecast is not fetched when current weather fails with no cache. This avoids a second timeout and keeps the error page simple.
- No OpenWeather weather-tile overlay on the map. The marker popup covers FR-12, and an overlay would need a backend tile proxy to keep the key private. Possible follow-up.
- Day labels use the location's local date, and "today" isn't singled out. The first and last days are usually partial.
- Carried over: UV index stays "Not available" (2.5 API). Guests see °C. Cached data is metric. LocMemCache. Dark-only theme. JS isn't unit-tested (no Node). Tests patch `weather.services.get_client` / `weather.services.now` and call `cache.clear()`.

## Verification
- Follow-ups TDD: 9 tests added. 6 failed first (the card always present and "Forecast unavailable" for skipped, failed, and no-key cases; the map's dashboard URL; the search link; the pin-preview script). 3 guards on existing behavior passed (weather requested only for the selected location, pin-style coordinates accepted, no "unavailable" text when data exists). All pass now.
- Tile fix TDD: 3 map tests (hidden fallback notice with attribution, unchanged site-wide `same-origin`, map script's `referrerPolicy`/`tileerror`) failed first, then passed.
- TDD: `weather/tests/test_forecast.py` (originally 25 tests) and a new client test first failed because the forecast client method, parser, and template sections were missing. All now pass. They cover local-date grouping (UTC−6 and +5:30), estimated high/low from `temp_max`/`temp_min`, partial-day labels, conditions, skipped/malformed samples, the 10-minute cache, stale fallback, separate current/forecast caches, °F conversion in text and chart data, forecast failure, a malformed forecast, and a missing key while current weather stays usable. They also cover the map's center, marker data, unit, Leaflet SRI, OSM attribution, the map shown when weather fails, and the API key absent from the page.
- `uv run python manage.py test` → 177 tests, OK (offline).
- `uv run python manage.py check` → no issues. `makemigrations --check` → no changes.
- Browser (user, Edge InPrivate): the marker and popup work, and the tiles were 403 before the fix. The tile fix hasn't been rechecked in the browser. The chart hasn't been checked with a live key.

## Browser checklist (needs a key)
1. Dashboard for "Paris, Texas": the chart draws with High/Low legend, the first day is selected, and the first and last days say "partial".
2. Clicking a chart column or day button updates the text panel. Tab reaches the day buttons, ←/→/Home/End move between days, and focus is visible.
3. Hovering a column shows a tooltip that stays inside the card. Resize to phone width: the day buttons fit and the chart redraws.
4. Switch to °F: the chart, buttons, panels, and map popup all show °F.
5. Map: tiles load, centered on the city. Drag/keyboard pan and +/− zoom work. The marker opens (click or Enter) with the name and conditions. The attribution is visible.
6. DevTools Network/console: no errors, no SRI block, and no request to openweathermap.org from the browser.
7. Pin preview: a single click drops a yellow pin with "View weather here", and no request is made until that link is followed. A double-click zooms without a pin, a drag pans without a pin, and clicking the main marker opens its popup without a pin. With a key, the link's dashboard shows the place name from OpenWeather.
8. Tiles: the Network panel shows each `tile.openstreetmap.org` request with `Referer: http://127.0.0.1:8000/` and status 200. Going offline after load and panning shows the "Map tiles couldn't load" notice.

## Next task
- Task 7: live API verification and demo prep. Add `OPENWEATHER_API_KEY` to `.env`, then:
  - Run the browser checklist above.
  - Live-check search (city, ambiguous, ZIP), device location, saving from search results, favorites, the unit toggle, and stale fallback (e.g. with the network off after a load).
  - Confirm the real `/data/2.5/forecast` shape matches the parser (`city.timezone`, `temp_min`/`temp_max`).
  - Fix anything found test-first, then prepare a short demo script.
