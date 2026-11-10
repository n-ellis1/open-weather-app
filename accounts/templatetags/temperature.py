from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter
def temperature(celsius, unit):
    """Format a cached metric temperature in the viewer's unit, e.g. "89°F".

    Weather is cached once per location in Celsius, so switching units never
    needs another OpenWeather call. Anything but "F" is shown in Celsius.
    """
    if celsius is None:
        return "Not available"
    if unit == "F":
        return f"{floatformat(celsius * 9 / 5 + 32, 0)}°F"
    return f"{floatformat(celsius, 0)}°C"
