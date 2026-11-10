# Weather App Handoff

## Current status (2026-11-09)
Milestone done: Task 4, registration, sign-in, and saved temperature preference (FR-1, FR-2, FR-3). The changes are uncommitted and awaiting review. Task 3 (postal search, device location) is committed in `54e2604`.

What changed:
- New `accounts` app, added to `INSTALLED_APPS` and mounted at `/accounts/`. Its migration is `accounts/migrations/0001_initial.py`, so run `migrate` on existing databases.
- `accounts/models.py`: `TemperaturePreference` (OneToOne user, `unit` "C"/"F"). A row is created only when the user picks a unit, and users with no row see Celsius. The helpers `temperature_unit_for(user)` and `set_temperature_unit(user, unit)` (`update_or_create` keyed on the given user) are the only paths to the table.
- `accounts/views.py` + `urls.py`:
  - `register` uses `UserCreationForm` with Django's password validators, signs the user in, and redirects to a safe `next` (otherwise to search). Signed-in users who open it go to search.
  - `login` is Django's `LoginView` with `redirect_authenticated_user`. Bad credentials show Django's standard error in a `role="alert"` box.
  - `logout` is Django's `LogoutView`, which only accepts POST.
  - `temperature_unit` is `@require_POST` + `@login_required` + CSRF. It accepts only "C" or "F" (anything else returns 400), saves the unit for `request.user`, and redirects to a same-host `next`.
- `settings.py`: `LOGIN_URL`, `LOGIN_REDIRECT_URL`, and `LOGOUT_REDIRECT_URL` (both redirects go to search). The context processor `accounts.context_processors.temperature_unit` is lazy, so it only queries the database when a template uses `temperature_unit`.
- `accounts/templatetags/temperature.py`: `{{ celsius|temperature:temperature_unit }}` returns "31°C", "89°F", or "Not available". The dashboard uses it for the current, feels-like, and detail-card temperatures. The weather cache is unchanged: one metric entry per location, shared by all users and units.
- Templates: `registration/login.html` and `registration/register.html` share the field partial `accounts/_form_fields.html`. Error and help ids match the `aria-describedby` and `aria-invalid` attributes Django generates. The `base.html` header shows "Sign in" and "Register" (with `?next=` set to the current page) for guests, and "Signed in as X" with a POST "Sign out" form for users. The dashboard shows signed-in users a `<fieldset>` with "Temperature unit" and two submit buttons using `aria-pressed`, labeled °C/°F with visually hidden "Celsius"/"Fahrenheit". Guests see a "Sign in to show temperatures in Fahrenheit" hint.
- `theme.css`: `.header-row`, `.account-nav`, `.button-small`, `.auth-card`, `.form-field`, `.field-errors`, `.unit-toggle`, and `.segmented(-option)`, all built from the existing tokens. README is updated.

## Decisions
- **Still open: One Call 3.0.** `/data/2.5/weather` has no UV index ("Not available"). UV (FR-7) and daily highs/lows (FR-8) need `/data/3.0/onecall`, which requires a separate subscription. Ask the user before building the forecast.
- When the forecast is built, render its temperatures with `|temperature:temperature_unit` (and pass the unit to the chart JS from the template). Keep cached data in metric.
- Guests always see °C. FR-3 makes the toggle a signed-in feature, so there's no session-only unit.
- Accounts use a username + password (Django default user). There's no email or password reset yet.
- A guest who POSTs the unit form is sent to sign-in with `next=/accounts/temperature-unit/` (a 405 if followed). In practice guests never see the form.
- Carried over: a two-letter qualifier is read as a US state. Geolocation links pass no name. JS isn't unit-tested (no Node). The cache is in-memory LocMemCache. The app is dark only. Tests patch `weather.services.get_client` / `weather.services.now` and call `cache.clear()`.
- `settings.py` has an unused `MAILERS` dict, which isn't a Django setting. Replace it with `EMAIL_BACKEND` if email is ever needed.

## Verification
- TDD: the new tests failed first with ImportError (`TemperaturePreference`), `NoReverseMatch` (no `accounts` namespace), and missing header text. They passed after implementation.
- New tests are in `accounts/tests/test_auth.py` and `test_temperature_preference.py` (41 tests). They cover registration (success, `next`, external `next`, mismatch, duplicate, weak password), sign-in errors (wrong password, unknown user, CSRF), POST-only sign-out, header links, guest access to search and the dashboard, the conversion filter, the default unit, saving and switching, persistence across sign-out/sign-in, ownership (one user's choice doesn't affect another, a posted `user` field is ignored), login/POST/CSRF/invalid-unit/open-redirect protection, a single OpenWeather call across unit changes and users, and the stale fallback in °F.
- `uv run python manage.py test` → 102 tests, OK (offline).
- `uv run python manage.py check` → no issues. `makemigrations --check` → no changes.
- Not yet clicked through in a real browser, and not run against the live API (no key yet).

## Next task
- Favorites (FR-9, FR-10, FR-11): a `Favorite` model (user FK, name, state, country, lat/lon; unique per user + coordinates). Add a POST + CSRF "Save" on search results and the dashboard, a sign-in-only "My favorites" list linking to the dashboard, and a POST remove. Scope every lookup to `request.user` (another user's id returns 404). Test first, including ownership.
- Follow-ups: the One Call 3.0 decision before FR-8, and a live check of search and the unit toggle once the API key is in `.env`.
