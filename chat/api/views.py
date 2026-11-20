from decimal import Decimal, InvalidOperation
import mimetypes
import os

from django.contrib.auth import get_user_model
from django.core.exceptions import SuspiciousFileOperation
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import get_valid_filename
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.forms import ReportForm
from chat.models import Attachment, Block, Conversation, Message
from chat.osm import search_places
from chat.services import sync_swap_cards, sync_swap_conversations
from chat.views import (
    DOC_EXTS, IMAGE_EXTS, MAX_UPLOAD,
    _blocked_state, _conversation_items, _get_conversation,
    _mark_sent, _normalize_image, _recent_messages, _send_denied,
)
from .authentication import CsrfExemptSessionAuthentication
from .serializers import (
    ConversationItemSerializer, MessageSerializer, UserMiniSerializer, profile_summary,
)

class ChatAPIView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAuthenticated]


class ConversationListAPI(ChatAPIView):
    def get(self, request):
        sync_swap_conversations(request.user)
        items = _conversation_items(request.user)
        data = ConversationItemSerializer(items, many=True, context={'request': request}).data
        return Response(data)


class MessageListCreateAPI(ChatAPIView):
    def get(self, request, conversation_id):
        conv = _get_conversation(request.user, conversation_id)  # non-peserta -> 404
        sync_swap_cards(conv)
        conv.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
        other = conv.other_user(request.user)
        blocked_by_me, blocked_me = _blocked_state(request.user, other)
        msgs = _recent_messages(conv, request.user)
        return Response({
            'conversation': {
                'id': conv.id,
                'other': profile_summary(other, request),
                'other_username': other.username,
                'item_id': conv.item_id,
                'item_name': conv.item_name,
                'accepted': conv.accepted,
                'is_request': (not conv.accepted) and request.user.pk == conv.user2_id,
                'blocked_by_me': blocked_by_me,
                'blocked_me': blocked_me,
            },
            'messages': MessageSerializer(msgs, many=True, context={'request': request}).data,
        })

    def post(self, request, conversation_id):
        conv = _get_conversation(request.user, conversation_id)
        denied = _send_denied(request.user, conv)
        if denied:
            return Response({'detail': denied.content.decode()}, status=denied.status_code)

        content = str(request.data.get('content', '')).strip()[:2000]
        if not content:
            return Response({'detail': 'Message cannot be empty.'}, status=400)

        reply_to = None
        raw = str(request.data.get('reply_to') or '')
        if raw.isdigit():
            reply_to = conv.visible_messages(request.user).filter(pk=int(raw)).first()

        msg = Message.objects.create(
            conversation=conv, sender=request.user, content=content,
            reply_to=reply_to, has_reply=reply_to is not None,
        )
        _mark_sent(conv, request.user)
        return Response(MessageSerializer(msg, context={'request': request}).data, status=201)