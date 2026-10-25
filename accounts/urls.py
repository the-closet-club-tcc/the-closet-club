
from django.urls import path
from .views import register, login_user, logout_view,profile

urlpatterns = [
    path("register/", register, name="register"),
    path("login/", login_user, name="login"),
    path("logout/", logout_view, name="logout"),
    path("profile/", profile, name="profile"),
]
