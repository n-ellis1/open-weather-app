# Weather App Handoff

## Current status (2026-11-09)
Milestone done: Task 5, favorite locations (FR-9, FR-10, FR-11). The changes are uncommitted and awaiting review. Task 4 (accounts, °C/°F preference) is committed in `159a8dd`.

What changed:
- New `favorites` app, added to `INSTALLED_APPS` and mounted at `/favorites/`. Its migration is `favorites/migrations/0001_initial.py`, so run `migrate` on existing databases.
- `favorites/models.py`:
  - `SavedLocation`: name, state, country_code, plus `lat`/`lon` stored as 4-decimal `DecimalField`s. They're unique together, so places are matched by coordinates.
  - `Favorite`: user FK + location FK, unique per (user, location). Rows are shared between users, and each user links to them through their own `Favorite`.
  - Helpers: `save_favorite(user, location)` (get-or-create; fills in a blank name), `favorite_coordinates(user)`, and `remove_favorite(fav)` (also deletes a `SavedLocation` once nobody has it saved). `SavedLocation.dashboard_query` builds the dashboard link.
- `favorites/views.py`:
  - `favorite_list`: `@login_required`. Filtered by `request.user` and makes no OpenWeather calls.
  - `save`: `@require_POST` + `@login_required` + CSRF. Validates input with `weather.views.location_from_params` (400 on bad coordinates), shows a success or "already in your favorites" message, and redirects to a same-host `next` (otherwise to Favorites).
  - `remove`: `@require_POST` + `@login_required` + CSRF. Uses `get_object_or_404(..., user=request.user)`, so another user's id returns 404.
- Renamed for reuse: `accounts.views._safe_next` → `safe_next`, and `weather.views._location_from_params` → `location_from_params`.
- `weather/views.py` passes `saved_coordinates` to the search and dashboard pages. The dashboard also passes `favorite_location`, which uses the report's place name when the URL has none (device location).
- Templates:
  - Search results: each result has a "☆ Save" form for signed-in users (with visually hidden "<label> to favorites"), or "★ Saved" if already saved. Guests see a sign-in hint.
  - Dashboard: "Save to favorites", or "★ In your favorites · View favorites". This shows even when weather fails to load.
  - `favorites/list.html`: links to the dashboard plus a Remove button per row, and an empty state that links to search.
  - Shared hidden fields are in `favorites/_location_fields.html`.
  - `base.html`: a "Favorites" header link for signed-in users (`aria-current` on that page), and Django messages rendered in a `role="status"` region.
- `theme.css`: `.result-action`, `.favorite-action`, `.saved-badge`, `.alert-success/info`, `.messages`, all built from existing tokens. README is updated.

## Decisions
- **Still open: One Call 3.0.** `/data/2.5/weather` has no UV index, and daily highs/lows (FR-8) need either `/data/3.0/onecall` (separate subscription) or the free `/data/2.5/forecast` (5 days in 3-hour steps, so daily high/low has to be aggregated). Ask the user before building the forecast.
- When the forecast is built, render its temperatures with `|temperature:temperature_unit` and pass the unit to the chart JS from the template. Keep cached data in metric.
- Favorites store the label at save time. Same coordinates mean the same favorite, even with a different label (the first name wins, and a blank name is filled in later). Saving from search re-runs the search on redirect, which costs one geocode call. Geocoding isn't cached.
- The dashboard is still public by coordinates. Only the favorites list and changes require sign-in.
- Carried over: guests always see °C. Accounts are username + password. A two-letter qualifier is read as a US state. JS isn't unit-tested (no Node). The cache is LocMemCache. The app is dark only. Tests patch `weather.services.get_client` / `weather.services.now` and call `cache.clear()`. The `MAILERS` setting is unused.

## Verification
- TDD: `favorites/tests/test_favorites.py` (37 tests) failed first with `ModuleNotFoundError: favorites.models`, then passed. They cover saving from search and from the dashboard (including device location and weather errors), the already-saved state, duplicate and re-rounded saves, same name with different coordinates, two users saving one place, list isolation, the header link, opening the correct location (the dashboard calls OpenWeather with the favorite's coordinates), removal, another user's id → 404, guest redirects, GET → 405, missing CSRF → 403, invalid coordinates → 400, a posted `user` field ignored, and open-redirect protection.
- `uv run python manage.py test` → 139 tests, OK (offline).
- `uv run python manage.py check` → no issues. `makemigrations --check` → no changes.
- Not yet clicked through in a real browser, and not run against the live API (no key yet).

## Next task
- Task 6: interactive multi-day forecast (FR-8) and weather map (FR-12). First ask the user which forecast endpoint to use (One Call 3.0 vs free 5-day/3-hour). The forecast needs a chart with keyboard-selectable days, a text table of each day's high/low/conditions, cached forecast data with the same 10-minute and stale-fallback rules, and the user's °C/°F unit. The map needs a library choice (e.g. Leaflet + OpenStreetMap tiles, which is a new dependency, so ask), centered on the selected location with a marker popup showing the name and current conditions. Weather tiles must be proxied so the API key never reaches the browser. Test first.
- Follow-up: once the API key is in `.env`, a live check of search, saving from search results, and the unit toggle.
