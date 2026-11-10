/*
 * "Use my location" (FR-6).
 *
 * The browser is asked for location only when the user clicks the button.
 * On success the page opens the weather dashboard with the device
 * coordinates; the backend then calls OpenWeather, so no API key is needed
 * here. On failure a status message explains what happened and the manual
 * search forms stay usable.
 */
(function () {
  "use strict";

  var container = document.getElementById("current-location");
  var button = document.getElementById("use-location");
  var hint = document.getElementById("use-location-hint");
  var status = document.getElementById("location-status");
  if (!container || !button || !status) {
    return;
  }

  var dashboardUrl = container.dataset.dashboardUrl;
  var STILL_SEARCH = " You can still search by city or postal code.";
  var busy = false;

  function show(message, isError) {
    status.textContent = message;
    status.classList.toggle("location-status-error", Boolean(isError));
  }

  function setBusy(value) {
    busy = value;
    // aria-disabled keeps keyboard focus on the button, unlike disabled.
    button.setAttribute("aria-disabled", value ? "true" : "false");
  }

  function onSuccess(position) {
    var params = new URLSearchParams({
      lat: position.coords.latitude.toFixed(4),
      lon: position.coords.longitude.toFixed(4),
    });
    show("Location found. Loading the weather…", false);
    window.location.assign(dashboardUrl + "?" + params.toString());
  }

  function onError(error) {
    var message;
    if (error.code === error.PERMISSION_DENIED) {
      message = "Location permission was denied. To use your location, allow it in your browser's site settings.";
    } else if (error.code === error.POSITION_UNAVAILABLE) {
      message = "Your location is unavailable right now.";
    } else if (error.code === error.TIMEOUT) {
      message = "Finding your location took too long.";
    } else {
      message = "We couldn't get your location.";
    }
    setBusy(false);
    show(message + STILL_SEARCH, true);
  }

  // Reveal the control only when this script runs.
  button.hidden = false;
  if (hint) {
    hint.hidden = false;
  }

  button.addEventListener("click", function () {
    if (busy) {
      return;
    }
    if (!window.isSecureContext) {
      show("Location is only available over HTTPS or on localhost." + STILL_SEARCH, true);
      return;
    }
    if (!("geolocation" in navigator)) {
      show("Your browser can't share your location." + STILL_SEARCH, true);
      return;
    }
    setBusy(true);
    show("Finding your location…", false);
    navigator.geolocation.getCurrentPosition(onSuccess, onError, {
      enableHighAccuracy: false,
      timeout: 10000,
      maximumAge: 600000,
    });
  });
})();
