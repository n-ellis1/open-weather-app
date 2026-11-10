from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


def convert_temperature(celsius, unit):
    """Return a metric temperature as a number in the viewer's unit ("F" or Celsius)."""
    return celsius * 9 / 5 + 32 if unit == "F" else celsius


@register.filter
def temperature(celsius, unit):
    """Format a cached metric temperature in the viewer's unit, e.g. "89°F".

    Weather is cached once per location in Celsius, so switching units never
    needs another OpenWeather call. Anything but "F" is shown in Celsius.
    """
    if celsius is None:
        return "Not available"
    symbol = "F" if unit == "F" else "C"
    return f"{floatformat(convert_temperature(celsius, unit), 0)}°{symbol}"
