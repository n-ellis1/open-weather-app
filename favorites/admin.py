from django.contrib import admin

from .models import Favorite, SavedLocation


@admin.register(SavedLocation)
class SavedLocationAdmin(admin.ModelAdmin):
    list_display = ("label", "lat", "lon")


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "location", "created_at")
    list_select_related = ("user", "location")
