from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_index, name='index'),
    path('<int:conversation_id>/', views.chat_index, name='room'),
    path('<int:conversation_id>/messages/', views.messages_partial, name='messages'),
    path('<int:conversation_id>/send/', views.send_message, name='send'),
    path('message/<int:message_id>/edit/', views.edit_message, name='edit'),
    path('message/<int:message_id>/delete/', views.delete_message, name='delete'),
]