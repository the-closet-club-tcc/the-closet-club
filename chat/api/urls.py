from django.urls import path
from . import views

urlpatterns = [
    path('conversations/', views.ConversationListAPI.as_view(), name='api_conversations'),
    path('conversations/start/', views.StartConversationAPI.as_view(), name='api_start'),
    path('conversations/<int:conversation_id>/messages/',
         views.MessageListCreateAPI.as_view(), name='api_messages'),
    path('conversations/<int:conversation_id>/accept/',
         views.AcceptConversationAPI.as_view(), name='api_accept'),
    path('conversations/<int:conversation_id>/delete/',
         views.DeleteConversationAPI.as_view(), name='api_delete_conversation'),
    path('conversations/<int:conversation_id>/block/',
         views.BlockAPI.as_view(), name='api_block'),
    path('conversations/<int:conversation_id>/unblock/',
         views.UnblockAPI.as_view(), name='api_unblock'),
    path('conversations/<int:conversation_id>/report/',
         views.ReportAPI.as_view(), name='api_report'),
    path('conversations/<int:conversation_id>/places/',
         views.PlaceSearchAPI.as_view(), name='api_places'),
    path('conversations/<int:conversation_id>/location/',
         views.SendLocationAPI.as_view(), name='api_location'),
    path('conversations/<int:conversation_id>/attach/',
         views.SendAttachmentAPI.as_view(), name='api_attach'),
    path('messages/<int:message_id>/edit/', views.MessageEditAPI.as_view(), name='api_edit'),
    path('messages/<int:message_id>/delete/',
         views.MessageDeleteAPI.as_view(), name='api_delete'),
    path('users/', views.UserSearchAPI.as_view(), name='api_users'),
]