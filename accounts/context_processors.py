from django.utils.functional import SimpleLazyObject

from .models import temperature_unit_for


def temperature_unit(request):
    """Expose the viewer's unit to every template (dashboard now, forecast later).

    Lazy, so pages that never show a temperature skip the database query.
    """
    return {"temperature_unit": SimpleLazyObject(lambda: str(temperature_unit_for(request.user)))}
