from django.urls import path

from . import views

urlpatterns = [
    path('items/', views.ClothingListAPI.as_view(), name='api_items'),
]
