from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path(
        "sign-in/",
        auth_views.LoginView.as_view(redirect_authenticated_user=True),
        name="login",
    ),
    # Django's LogoutView only accepts POST.
    path("sign-out/", auth_views.LogoutView.as_view(), name="logout"),
    path("temperature-unit/", views.temperature_unit, name="temperature_unit"),
]
