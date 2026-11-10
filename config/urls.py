from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("favorites/", include("favorites.urls")),
    path("", include("weather.urls")),
]
