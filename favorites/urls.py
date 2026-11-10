from django.urls import path

from . import views

app_name = "favorites"

urlpatterns = [
    path("", views.favorite_list, name="list"),
    path("save/", views.save, name="save"),
    path("<int:pk>/remove/", views.remove, name="remove"),
]
