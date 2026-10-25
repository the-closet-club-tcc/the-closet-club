from django.urls import path
from . import views

app_name = 'swap'

urlpatterns = [
    path('', views.swap_page, name='index'),
]