# Open Weather App Requirements

Build a weather web app that lets users find a location, see its current
weather and forecast, and save places they check often.

## Functional Requirements

- FR-1 Account registration. Let new users create an account.
- FR-2 Sign in. Let users sign in and show an error for incorrect credentials.
- FR-3 Temperature preference. Let signed-in users switch between Celsius and
  Fahrenheit, update the current and forecast temperatures, and save their
  choice for future visits.
- FR-4 Location search. Let users search by city name or ZIP/postal code.
- FR-5 Multiple matches. Show the city, state or region when available, and
  country for each match so users can choose the correct location.
- FR-6 Current location. Use device coordinates with permission to show local
  weather. Keep manual search available if permission is denied or location
  is unavailable.
- FR-7 Current weather. Show temperature, feels-like temperature, humidity,
  wind speed, UV index, cloud cover, pressure, and sunrise and sunset times
  when available.
- FR-8 Multi-day forecast. Show an interactive forecast chart. Let users
  select a day to view its predicted high, low, and weather conditions.
- FR-9 Save a favorite. Let signed-in users save a location from either the
  search results or the weather dashboard.
- FR-10 Switch to a favorite. Let signed-in users open their personal favorites
  list and select a location to see its current weather and forecast.
- FR-11 Remove a favorite. Let signed-in users remove a location from their list.
- FR-12 Interactive map. Center the map on the selected location. Let users
  pan, zoom, and select a weather marker to see the location name and
  current conditions.

## Non-Functional Requirements

- NFR-1 Performance and caching. Reuse successful server-cached weather for the
  same location for 10 minutes to reduce loading time and OpenWeather calls.
- NFR-2 Security. Store secrets in a gitignored .env file at the repo root.
  Send all OpenWeather requests from the backend. Restrict saved locations and
  temperature preferences to their owner.
- NFR-3 Reliability. If OpenWeather times out or returns an error, show a clear
  message and let the user retry or search again. If older cached weather is
  available for that location, show it with its last-updated time.
- NFR-4 Usability and accessibility. Support desktop and mobile layouts,
  clearly labeled controls, keyboard navigation, and forecast details in text.

## Project Constraints

- Use OpenWeather as the weather provider.
- Document the tech stack in README.md and AGENTS.md.
- Follow the test-driven workflow in AGENTS.md and mock OpenWeather in tests.
- Implement one milestone at a time. HANDOFF.md identifies the current task.