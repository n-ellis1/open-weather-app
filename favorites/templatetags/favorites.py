from django import template

register = template.Library()


@register.filter
def is_saved(location, saved_coordinates):
    """True when a location's coordinates are in the viewer's favorites."""
    return (location.lat, location.lon) in (saved_coordinates or ())
