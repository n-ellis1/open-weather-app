/*
 * Interactive multi-day forecast (FR-8).
 *
 * The server renders every day as text (one panel per day), so the forecast
 * reads fine without JavaScript. This script turns the panels into tabs, one
 * per day, and draws an SVG chart of the estimated highs and lows. Days can be
 * selected by clicking a chart column or a day button, and with the arrow,
 * Home, and End keys. Temperatures in #forecast-data are already in the
 * viewer's unit.
 */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var HEIGHT = 220;
  var PAD_TOP = 30;
  var PAD_BOTTOM = 30;

  var dataNode = document.getElementById("forecast-data");
  var chart = document.querySelector("[data-forecast-chart]");
  var tablist = document.querySelector(".forecast-days");
  if (!dataNode || !chart || !tablist) return;

  var data;
  try {
    data = JSON.parse(dataNode.textContent);
  } catch (error) {
    return;
  }
  var days = data && data.days ? data.days : [];
  if (!days.length) return;

  var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
  var panels = tabs.map(function (tab) {
    return document.getElementById(tab.getAttribute("aria-controls"));
  });
  var svg = chart.querySelector(".chart-svg");
  var tooltip = chart.querySelector(".chart-tooltip");
  var symbol = "°" + (data.unit === "F" ? "F" : "C");
  var selected = 0;

  function format(value) {
    return Math.round(value) + symbol;
  }

  function el(name, attrs, parent) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    if (parent) parent.appendChild(node);
    return node;
  }

  function niceStep(range) {
    var raw = range / 3;
    var magnitude = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var steps = [1, 2, 5, 10];
    for (var i = 0; i < steps.length; i++) {
      if (steps[i] * magnitude >= raw) return steps[i] * magnitude;
    }
    return 10 * magnitude;
  }

  function draw() {
    var width = Math.max(svg.parentNode.clientWidth, 240);
    var column = width / days.length;
    var lows = days.map(function (d) { return d.low; });
    var highs = days.map(function (d) { return d.high; });
    var step = niceStep(Math.max(Math.max.apply(null, highs) - Math.min.apply(null, lows), 3));
    var min = Math.floor(Math.min.apply(null, lows) / step) * step;
    var max = Math.ceil(Math.max.apply(null, highs) / step) * step;
    if (max === min) max = min + step;

    function x(i) { return (i + 0.5) * column; }
    function y(value) {
      return PAD_TOP + (1 - (value - min) / (max - min)) * (HEIGHT - PAD_TOP - PAD_BOTTOM);
    }

    svg.setAttribute("viewBox", "0 0 " + width + " " + HEIGHT);
    svg.setAttribute("width", width);
    svg.setAttribute("height", HEIGHT);
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    // Selected-day highlight and per-day hit targets (the whole column).
    days.forEach(function (day, i) {
      var hit = el("rect", {
        "class": "chart-column" + (i === selected ? " is-selected" : ""),
        x: i * column + 1, y: 0, width: column - 2, height: HEIGHT, rx: 4,
      }, svg);
      hit.addEventListener("click", function () { select(i, true); });
      hit.addEventListener("mousemove", function (event) { showTooltip(i, event); });
      hit.addEventListener("mouseleave", hideTooltip);
    });

    // Recessive gridlines with tick labels drawn inside the plot.
    for (var tick = min; tick <= max + step / 2; tick += step) {
      el("line", { "class": "chart-grid", x1: 0, x2: width, y1: y(tick), y2: y(tick) }, svg);
      var label = el("text", { "class": "chart-tick", x: 4, y: y(tick) - 4 }, svg);
      label.textContent = Math.round(tick) + "°";
    }

    [["high", highs], ["low", lows]].forEach(function (series) {
      var points = series[1].map(function (value, i) { return x(i) + "," + y(value); }).join(" ");
      el("polyline", { "class": "chart-line chart-line-" + series[0], points: points }, svg);
    });

    days.forEach(function (day, i) {
      el("circle", { "class": "chart-point chart-point-high", cx: x(i), cy: y(day.high), r: 5 }, svg);
      el("circle", { "class": "chart-point chart-point-low", cx: x(i), cy: y(day.low), r: 5 }, svg);
    });

    // Direct labels for the selected day only.
    var day = days[selected];
    var high = el("text", { "class": "chart-value", x: x(selected), y: y(day.high) - 12, "text-anchor": "middle" }, svg);
    high.textContent = format(day.high);
    var low = el("text", { "class": "chart-value", x: x(selected), y: y(day.low) + 22, "text-anchor": "middle" }, svg);
    low.textContent = format(day.low);

    // Points and labels shouldn't block clicks on the columns beneath.
    Array.prototype.forEach.call(svg.querySelectorAll("line, polyline, circle, text"), function (node) {
      node.style.pointerEvents = "none";
    });
  }

  function showTooltip(i, event) {
    var day = days[i];
    tooltip.textContent = day.label + " · High " + format(day.high) + " · Low " + format(day.low) +
      (day.description ? " · " + day.description : "") + (day.partial ? " · partial day" : "");
    tooltip.hidden = false;
    var box = svg.parentNode.getBoundingClientRect();
    var left = event.clientX - box.left + 12;
    var maxLeft = box.width - tooltip.offsetWidth - 4;
    tooltip.style.left = Math.max(4, Math.min(left, maxLeft)) + "px";
    tooltip.style.top = Math.max(4, event.clientY - box.top - tooltip.offsetHeight - 12) + "px";
  }

  function hideTooltip() {
    tooltip.hidden = true;
  }

  function select(index, moveFocus) {
    selected = index;
    tabs.forEach(function (tab, i) {
      var active = i === index;
      tab.setAttribute("aria-selected", active ? "true" : "false");
      tab.tabIndex = active ? 0 : -1;
      if (panels[i]) panels[i].hidden = !active;
    });
    if (moveFocus) tabs[index].focus();
    draw();
  }

  tabs.forEach(function (tab, i) {
    tab.addEventListener("click", function () { select(i, false); });
    tab.addEventListener("keydown", function (event) {
      var next = null;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (i + 1) % tabs.length;
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (i - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      if (next === null) return;
      event.preventDefault();
      select(next, true);
    });
  });

  panels.forEach(function (panel) {
    if (panel) panel.tabIndex = 0;
  });
  tablist.style.setProperty("--forecast-days", days.length);
  tablist.hidden = false;
  chart.hidden = false;
  var hint = document.querySelector(".forecast-js-hint");
  if (hint) hint.hidden = false;
  select(0, false);

  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(draw, 100);
  });
})();
