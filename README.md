# Open Weather App

A weather web app for finding a location, viewing its current weather and
forecast, and saving places you check often. See `REQUIREMENTS.md` for the
full feature list and `HANDOFF.md` for current progress.

## Tech stack

- **Python 3.13+** managed with **uv**
- **Django 6.1** with server-rendered Django templates
- **SQLite** for users, temperature preferences, and favorites
- **Django authentication** for registration and sign-in
- **JavaScript** for browser geolocation ("Use my location"); the interactive
  forecast and the map are planned
- **OpenWeather** as the weather provider, called only from the backend
  (`weather/openweather.py`) using Python's standard-library HTTP client with a timeout

## Project layout

```
config/            Django settings and root URLs
weather/           Weather app
  openweather.py   Backend OpenWeather HTTP client (the only code that calls OpenWeather)
  services.py      Weather service: location lookup, current weather, 10-minute cache
                   with stale fallback (Django local-memory cache)
  views.py         Input validation and rendering
  templates/       Page templates
  tests/           Offline tests (OpenWeather is always mocked)
accounts/          Registration, sign-in/out (Django auth), and the °C/°F preference
  models.py        TemperaturePreference (one per user; Celsius when unset)
  templatetags/    `temperature` filter: converts cached metric values for display
  context_processors.py  Puts the viewer's `temperature_unit` in every template
templates/         Shared base template
static/css/        Shared dark theme (theme.css)
static/js/         Browser scripts (current-location.js for "Use my location")
```

## Setup

1. Install [uv](https://docs.astral.sh/uv/).
2. Install dependencies (uv also installs a compatible Python if needed):

   ```
   uv sync
   ```

3. Create your local environment file:

   ```
   cp .env.example .env        # macOS/Linux
   Copy-Item .env.example .env # Windows PowerShell
   ```

   Edit `.env` and set `DJANGO_SECRET_KEY` and `OPENWEATHER_API_KEY`.
   `.env` is gitignored, so keep real secrets only there.

   The app and the tests run without an OpenWeather key. Without one,
   searches show a message explaining that live search needs a key. With
   `DJANGO_DEBUG=true` and no `DJANGO_SECRET_KEY`, a development-only
   secret key is used.

4. Create the SQLite database:

   ```
   uv run python manage.py migrate
   ```

## Run

```
uv run python manage.py runserver
```

Open http://127.0.0.1:8000/ and search for a city such as "Paris", or a
ZIP/postal code such as "90210" with "United States" selected, then select a
result to open its current-weather dashboard. "Use my location" asks the
browser for permission and opens the dashboard for your coordinates. Browsers
only share location on HTTPS or localhost, so use http://127.0.0.1:8000/ or
http://localhost:8000/ locally.

Search and the dashboard work without an account. Use **Register** in the
header to create one; signed-in users get a °C/°F toggle on the dashboard,
and the choice is saved to their account. Weather is cached once per location
in metric and converted when the page is drawn, so switching units doesn't
call OpenWeather again.

## Test

```
uv run python manage.py test
```

Tests run offline. View and service tests mock the OpenWeather client, and
client tests mock the HTTP transport, so no API key or network is needed.
