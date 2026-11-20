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

class StartConversationAPI(ChatAPIView):
    def post(self, request):
        raw = str(request.data.get('user_id', ''))
        if not raw.isdigit():
            return Response({'detail': 'A valid user_id is required.'}, status=400)
        other = get_object_or_404(get_user_model(), pk=int(raw))
        if other == request.user:
            return Response({'detail': 'You cannot message yourself.'}, status=400)
        if any(_blocked_state(request.user, other)):
            return Response({'detail': 'Cannot start conversation with this user.'}, status=403)

        conv = Conversation.objects.filter(
            Q(user1=request.user, user2=other) | Q(user1=other, user2=request.user)
        ).first()
        if conv is None:
            conv = Conversation.objects.create(user1=request.user, user2=other, accepted=False)

        item_id = str(request.data.get('item_id', ''))
        if item_id.isdigit():
            conv.item_id = int(item_id)
            conv.item_name = str(request.data.get('item_name', ''))[:150]
            conv.save()
        return Response({'id': conv.id, 'username': other.username})


class UserSearchAPI(ChatAPIView):
    def get(self, request):
        q = request.query_params.get('q', '').strip()[:50]
        blocked_ids = set(
            Block.objects.filter(blocker=request.user).values_list('blocked_id', flat=True)
        ) | set(
            Block.objects.filter(blocked=request.user).values_list('blocker_id', flat=True)
        )
        qs = get_user_model().objects.exclude(pk=request.user.pk).exclude(pk__in=blocked_ids)
        if q:
            qs = qs.filter(username__icontains=q)
        users = qs.order_by('username')[:20]
        return Response(UserMiniSerializer(users, many=True, context={'request': request}).data)

class MessageEditAPI(ChatAPIView):
    def post(self, request, message_id):
        msg = get_object_or_404(
            Message, pk=message_id, sender=request.user, message_type='text',
        )
        _get_conversation(request.user, msg.conversation_id)
        content = str(request.data.get('content', '')).strip()[:2000]
        if not content:
            return Response({'detail': 'Message cannot be empty.'}, status=400)
        if content != msg.content:
            msg.content = content
            msg.is_edited = True
            msg.save()
        return Response(MessageSerializer(msg, context={'request': request}).data)


class MessageDeleteAPI(ChatAPIView):
    def post(self, request, message_id):
        msg = get_object_or_404(
            Message.objects.exclude(message_type='swap'),
            pk=message_id, sender=request.user,
        )
        _get_conversation(request.user, msg.conversation_id)
        msg.delete()
        return Response({'status': 'ok'})    