# Open Weather Application

## Stack and scope

- Use Python, Django, SQLite, and uv. Render pages with Django templates and use JavaScript for browser geolocation, the interactive forecast, and the map. The map uses Leaflet 1.9.4 (unpkg, with SRI) and OpenStreetMap tiles.
- Use Django authentication for registration and sign-in. Keep the user's temperature preference and favorites in SQLite. Each favorite belongs to one user and references one location.
- Follow the documented FR-1 through FR-12 and NFR-1 through NFR-4. Ask before changing a requirement or adding a major dependency.

## Architecture

- Keep Django views focused on input validation, permissions, and rendering. Put location lookup, weather retrieval, and caching in a weather service. Route all OpenWeather requests through a backend OpenWeather client.
- Use the selected location's coordinates for current weather and forecasts. Show distinguishing location details when a search returns multiple matches.
- Reuse successful cached weather for 10 minutes. Keep the last successful response and timestamp beyond that freshness window so an upstream failure can show older data with its last-updated time. If no fallback is available, show a clear error and offer retry or a new search.
- Keep location search available if device location permission is denied. Provide text forecast details and keyboard-accessible controls.

## Security

- Read the OpenWeather API key and Django secret key from environment variables. Keep local secrets in a root .env file, exclude it with .gitignore, and use placeholders in .env.example.
- Keep API keys out of browser code, browser requests, rendered responses, and logs. Set a timeout for upstream requests.
- Require sign-in for preferences and favorites. Scope favorite lookups and changes to the current user. Use POST and Django CSRF protection for changes.

## Test-driven workflow

1. Pick one small user-visible behavior. Write a test and run it to verify it fails for the expected reason.
2. Implement the behavior and rerun the test. Refactor once it passes, then run the full suite with `uv run python manage.py test`.
3. Keep tests offline. Mock the OpenWeather client in view and service tests. Mock HTTP transport in client tests. Use a controlled clock or cache fixtures to test freshness and stale fallback.
4. Cover ambiguous searches, favorite ownership, saved unit preferences, cache hits, and upstream failures. Report the commands run and their results.
