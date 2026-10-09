from django.urls import path
from accounts.views import *

urlpatterns = [
    path('register/', register, name='register'),
]