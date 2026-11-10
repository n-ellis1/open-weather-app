/*
 * Weather map (FR-12), drawn with Leaflet and OpenStreetMap tiles.
 *
 * The map centers on the selected coordinates from #map-data. Its marker
 * opens a popup with the location name and current conditions (already in
 * the viewer's unit). No OpenWeather request or API key is involved here.
 */
(function () {
  "use strict";

  var container = document.getElementById("weather-map");
  var dataNode = document.getElementById("map-data");
  if (!container || !dataNode || typeof window.L === "undefined") return;

  var data;
  try {
    data = JSON.parse(dataNode.textContent);
  } catch (error) {
    return;
  }
  if (typeof data.lat !== "number" || typeof data.lon !== "number") return;

  var fallback = container.querySelector(".map-fallback");
  if (fallback) fallback.remove();

  var map = L.map(container, { scrollWheelZoom: false }).setView([data.lat, data.lon], 10);
  // OpenStreetMap's tile usage policy requires a valid Referer. Django's
  // site-wide Referrer-Policy (same-origin) would strip it from these
  // cross-origin requests, so only the tile images send the page's origin
  // (e.g. "http://127.0.0.1:8000/"), never its path or query.
  var tiles = L.tileLayer(container.dataset.tileUrl, {
    maxZoom: 19,
    attribution: container.dataset.attribution,
    referrerPolicy: "strict-origin-when-cross-origin",
  }).addTo(map);

  // Tell the user when tiles fail to load (offline, blocked, network errors).
  // The marker, popup, and attribution keep working without tiles. OSM's own
  // "Access blocked" tiles arrive as normal images, so they can't be detected.
  var tileNotice = document.querySelector(".map-tile-error");
  var failedInBatch = 0;
  tiles.on("loading", function () { failedInBatch = 0; });
  tiles.on("tileerror", function () {
    failedInBatch += 1;
    if (tileNotice) tileNotice.hidden = false;
  });
  tiles.on("load", function () {
    if (tileNotice && failedInBatch === 0) tileNotice.hidden = true;
  });

  // Only zoom on the scroll wheel once the map is in use, so the page scrolls normally.
  map.on("focus click", function () { map.scrollWheelZoom.enable(); });
  map.on("blur mouseout", function () { map.scrollWheelZoom.disable(); });

  // Build the popup with text nodes so names from the URL can't inject HTML.
  var popup = document.createElement("div");
  popup.className = "map-popup";
  var title = document.createElement("strong");
  title.textContent = data.name;
  popup.appendChild(title);
  var conditions = document.createElement("p");
  conditions.textContent = data.conditions || "Current conditions are not available.";
  popup.appendChild(conditions);

  L.marker([data.lat, data.lon], {
    title: data.name,
    alt: "Weather marker for " + data.name,
    keyboard: true,
  }).addTo(map).bindPopup(popup);
})();
