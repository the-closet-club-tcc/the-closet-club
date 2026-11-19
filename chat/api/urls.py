from django.urls import path
from . import views

urlpatterns = [
    path('conversations/', views.ConversationListAPI.as_view(), name='api_conversations'),
    path('conversations/<int:conversation_id>/messages/',
         views.MessageListCreateAPI.as_view(), name='api_messages'),
]