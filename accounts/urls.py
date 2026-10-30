
from django.urls import path
from .views import (
    register, 
    login_user, 
    logout_view,profile, 
    edit_profile,
    delete_account,
    public_profile,
    request_verification,
    add_review,
)

urlpatterns = [
    path("register/", register, name="register"),
    path("login/", login_user, name="login"),
    path("logout/", logout_view, name="logout"),
    path("profile/", profile, name="profile"),
    path("edit-profile/", edit_profile, name="edit_profile"),
    path("delete-account/", delete_account, name="delete_account"),
    path("user/<str:username>/", public_profile, name="public_profile"),
    path("request-verification/", request_verification, name="request_verification"),
    path("review/<str:username>/", add_review, name="add_review"),
]
