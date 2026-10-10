from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_index, name='index'),
    path('<int:conversation_id>/', views.chat_index, name='room'),
]