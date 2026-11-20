from django.urls import path
from . import api_views

urlpatterns = [
    path("users/", api_views.UserListAPIView.as_view(), name="api_user_list"),
    path("profile/", api_views.CurrentUserProfileAPIView.as_view(), name="api_current_profile"),
    path("users/<str:username>/", api_views.PublicProfileAPIView.as_view(), name="api_public_profile"),
    path("users/<str:username>/reviews/", api_views.UserReviewsAPIView.as_view(), name="api_user_reviews"),
    path("verification/", api_views.VerificationStatusAPIView.as_view(), name="api_verification_status"),
]