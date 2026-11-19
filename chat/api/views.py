from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.models import Message
from chat.services import sync_swap_cards, sync_swap_conversations
from chat.views import (
    _blocked_state, _conversation_items, _get_conversation,
    _mark_sent, _recent_messages, _send_denied,
)
from .authentication import CsrfExemptSessionAuthentication
from .serializers import ConversationItemSerializer, MessageSerializer


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
                'other_username': other.username,
                'item_name': conv.item_name,
                'accepted': conv.accepted,
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