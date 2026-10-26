
from django.urls import path
from .views import (
    register, 
    login_user, 
    logout_view,profile, 
    edit_profile,
    public_profile,
    request_verification,
)

urlpatterns = [
    path("register/", register, name="register"),
    path("login/", login_user, name="login"),
    path("logout/", logout_view, name="logout"),
    path("profile/", profile, name="profile"),
    path("edit-profile/", edit_profile, name="edit_profile"),
    path("user/<str:username>/", public_profile, name="public_profile"),
    path("request-verification/", request_verification, name="request_verification"),
]
