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
    path('start/<int:user_id>/', views.start_conversation, name='start'),
    path('<int:conversation_id>/places/', views.place_search, name='places'),
    path('<int:conversation_id>/location/', views.send_location, name='send_location'),
    path('<int:conversation_id>/attach/', views.send_attachment, name='send_attachment'),
    path('attachment/<int:message_id>/', views.attachment, name='attachment'),    
]