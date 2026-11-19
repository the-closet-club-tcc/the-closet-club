from django.urls import reverse
from rest_framework import serializers

from chat.models import Message


class UserMiniSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    is_verified = serializers.SerializerMethodField()

    def get_is_verified(self, obj):
        return bool(getattr(obj, 'is_verified', False))


class ReplyPreviewSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sender = serializers.CharField(source='sender.username')
    preview = serializers.SerializerMethodField()

    def get_preview(self, obj):
        return obj.preview_text()


class MessageSerializer(serializers.ModelSerializer):
    sender = UserMiniSerializer(read_only=True)
    reply_to = ReplyPreviewSerializer(read_only=True)
    swap_request = serializers.PrimaryKeyRelatedField(read_only=True)
    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)
    attachment_url = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'sender', 'message_type', 'content',
            'place_name', 'address', 'latitude', 'longitude',
            'is_edited', 'is_read', 'created_at',
            'attachment_name', 'attachment_type', 'attachment_size', 'attachment_url',
            'reply_to', 'swap_request',
        ]

    def get_attachment_url(self, obj):
        if obj.message_type not in (Message.MessageType.IMAGE, Message.MessageType.FILE):
            return None
        path = reverse('chat:attachment', args=[obj.pk])
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request else path


class ConversationItemSerializer(serializers.Serializer):
    """Membungkus dict dari _conversation_items() di chat/views.py."""
    id = serializers.IntegerField(source='conversation.id')
    other = UserMiniSerializer()
    item_id = serializers.IntegerField(source='conversation.item_id', allow_null=True)
    item_name = serializers.CharField(source='conversation.item_name')
    accepted = serializers.BooleanField(source='conversation.accepted')
    preview = serializers.CharField()
    last_time = serializers.DateTimeField()
    unread = serializers.IntegerField()