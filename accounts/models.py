from django.conf import settings
from django.db import models


class TemperatureUnit(models.TextChoices):
    CELSIUS = "C", "Celsius"
    FAHRENHEIT = "F", "Fahrenheit"


class TemperaturePreference(models.Model):
    """A signed-in user's display unit (FR-3). Weather stays cached in metric.

    Users without a row see Celsius, so a row is only created when they choose.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="temperature_preference",
    )
    unit = models.CharField(
        max_length=1,
        choices=TemperatureUnit.choices,
        default=TemperatureUnit.CELSIUS,
    )

    def __str__(self):
        return f"{self.user}: °{self.unit}"


def temperature_unit_for(user):
    """Return the unit code ("C" or "F") to show this user; Celsius by default."""
    if not user.is_authenticated:
        return TemperatureUnit.CELSIUS
    preference = TemperaturePreference.objects.filter(user=user).only("unit").first()
    return preference.unit if preference else TemperatureUnit.CELSIUS


def set_temperature_unit(user, unit):
    """Save the user's unit. Only ever touches the given user's row."""
    TemperaturePreference.objects.update_or_create(user=user, defaults={"unit": unit})
