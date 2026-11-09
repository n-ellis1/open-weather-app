# Weather App Handoff

## Current status (2026-11-09)
Milestone done: Django/uv/SQLite setup + city search with multiple matches (FR-4 city part, FR-5). Uncommitted, awaiting review.

What changed:
- uv project (`pyproject.toml`, `uv.lock`), Django 6.1.3, SQLite. Project `config/`, app `weather/`.
- `config/settings.py` loads a root `.env` (small built-in loader, no extra dependency). Reads `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `OPENWEATHER_API_KEY`, `OPENWEATHER_TIMEOUT_SECONDS`. Without a secret key and with debug on, it uses a dev-only key. With debug off, a missing key raises an error.
- `weather/openweather.py`: backend client using stdlib `urllib` with a timeout (no `requests`/`httpx` dependency). `geocode_city()` calls `/geo/1.0/direct` (limit 5). It raises `MissingAPIKeyError` before any request when no key is set, and `OpenWeatherError` on HTTP, network, timeout, or bad JSON. Errors and logs never include the URL or key (`from None`).
- `weather/services.py`: `get_client()`, `Location` dataclass with `label` ("City, State, Country"), `search_locations()` (removes duplicate and malformed matches). `weather/countries.py` maps ISO codes to country names and falls back to the code.
- `weather/views.py` `search` at `/`: GET `?q=`. Handles empty, too long (>100 chars), missing key (clear message), upstream error (message + "Try again" link + search form), and no matches.
- Templates: `templates/base.html` (skip link, header), `weather/templates/weather/search.html`.
- README.md, `.gitignore` (excludes `.env`, `db.sqlite3`, `.venv`), and `.env.example` (placeholders only).

## Decisions
- **Dark theme:** `static/css/theme.css` is the one shared stylesheet. Colors and spacing are CSS custom properties on `:root` with AA-contrast text. It sets a yellow `:focus-visible` outline (3px) on all controls, uses labeled inputs with hints, and includes reusable `.card`, `.button`/`.button-secondary`, `.alert-error`/`.alert-warning`, `.result-list`/`.result-item`, `.visually-hidden`, and a mobile breakpoint that stacks `.field-row`. The dashboard should extend `base.html` and reuse these tokens and classes. It does not follow the OS light/dark preference; the app is dark only for now.
- Search results show full country names (FR-5) plus lat/lon as extra distinguishing details. The service carries coordinates for use in later weather lookups.
- Results are plain text for now; they don't link anywhere yet.
- Tests patch `weather.services.get_client` (view/service) or pass an `opener` / patch `weather.openweather.urlopen` (client).

## Verification
- TDD: wrote `test_search_for_paris_lists_texas_and_france_as_distinct_results` first. It failed as expected (`geocode_city` called 0 times), then passed after implementation.
- `uv run python manage.py test` → 18 tests, OK (offline).
- `uv run python manage.py check` → no issues. Live smoke test on runserver without a key: `/?q=Paris` showed the missing-key message, and `theme.css` returned 200.
- Not yet tested against the real OpenWeather API (no key yet).

## Next task (proposed)
- Select a search result to open a weather dashboard for its coordinates showing current weather (FR-7) via the weather service, with 10-minute cache reuse and stale fallback (NFR-1, NFR-3). Mock the client and use a controlled clock in tests.
- Small follow-ups to consider: ZIP/postal code search (FR-4, `/geo/1.0/zip`), and a live check of search once the API key is added.
