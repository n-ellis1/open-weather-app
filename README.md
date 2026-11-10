# Open Weather App

A weather web app for finding a location, viewing its current weather and
forecast, and saving places you check often. See `REQUIREMENTS.md` for the
full feature list and `HANDOFF.md` for current progress.

## Tech stack

- **Python 3.13+** managed with **uv**
- **Django 6.1** with server-rendered Django templates
- **SQLite** for users, temperature preferences, and favorites
- **Django authentication** for registration and sign-in
- **JavaScript** for browser geolocation ("Use my location"), the interactive
  forecast chart (hand-drawn SVG, no chart library), and the map
- **Leaflet 1.9.4** (loaded from unpkg with Subresource Integrity) and
  **OpenStreetMap** tiles for the weather map
- **OpenWeather** as the weather provider, called only from the backend
  (`weather/openweather.py`) using Python's standard-library HTTP client with a timeout

## Project layout

```
config/            Django settings and root URLs
weather/           Weather app
  openweather.py   Backend OpenWeather HTTP client (the only code that calls OpenWeather)
  services.py      Weather service: location lookup, current weather, 5-day forecast
                   grouped by local date, 10-minute cache with stale fallback
                   (Django local-memory cache)
  views.py         Input validation and rendering
  templates/       Page templates
  tests/           Offline tests (OpenWeather is always mocked)
accounts/          Registration, sign-in/out (Django auth), and the °C/°F preference
  models.py        TemperaturePreference (one per user; Celsius when unset)
  templatetags/    `temperature` filter: converts cached metric values for display
  context_processors.py  Puts the viewer's `temperature_unit` in every template
favorites/         Saved locations (sign-in only)
  models.py        SavedLocation (unique rounded lat/lon) and Favorite (one per user + place)
  views.py         Favorites list, POST save, POST remove (scoped to the signed-in user)
templates/         Shared base template
static/css/        Shared dark theme (theme.css)
static/js/         Browser scripts: current-location.js ("Use my location"),
                   forecast-chart.js (interactive forecast), weather-map.js (Leaflet map)
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

Signed-in users can also **Save** a location from the search results or the
dashboard. **Favorites** in the header lists their saved places; select one
to open its dashboard, or use **Remove** to delete it. Places are matched by
coordinates, so Paris, Texas and Paris, France are separate favorites, and
saving the same place twice keeps a single entry.

Below current conditions, the dashboard shows a **5-day forecast** from
OpenWeather's free 5-day / 3-hour endpoint. Samples are grouped by the
location's local date, each day's high and low are estimated from its samples,
and days the forecast window only partly covers are labelled "Partial day".
Select a day in the chart or with the day buttons (arrow keys move between
days) to read its high, low, and conditions. If the forecast can't be loaded,
current weather still shows, and the forecast card says "Forecast
unavailable". The **map** (Leaflet + OpenStreetMap tiles) is centered on the
location; select the marker for its name and current conditions. Click any
other point to drop a preview pin, then choose **View weather here** to open
the dashboard for those coordinates. Weather is only requested after that
choice.

## Test

```
uv run python manage.py test
```

Tests run offline. View and service tests mock the OpenWeather client, and
client tests mock the HTTP transport, so no API key or network is needed.
