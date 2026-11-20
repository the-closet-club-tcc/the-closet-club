from django.urls import reverse
from rest_framework import serializers

from chat.models import Message


def absolute_url(file_field, request):
    """Return an absolute URL for an image/file field, or None when empty."""
    if not file_field:
        return None
    try:
        url = file_field.url
    except ValueError:
        return None
    if request and url.startswith('/'):
        return request.build_absolute_uri(url)  # local: /media/... becomes absolute
    return url  # Cloudinary URLs are already absolute


class UserMiniSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    is_verified = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    def get_is_verified(self, obj):
        return bool(getattr(obj, 'is_verified', False))

    def get_avatar(self, obj):
        return absolute_url(obj.foto_profil, self.context.get('request'))


def profile_summary(user, request):
    """UserMini data plus review statistics, used in the chat room header."""
    data = dict(UserMiniSerializer(user, context={'request': request}).data)
    count = user.reviews_received.count()
    rating = None
    if count:
        raw = user.get_rata_rata_rating
        raw = raw() if callable(raw) else raw
        try:
            rating = float(raw)
        except (TypeError, ValueError):
            rating = None
    data['review_count'] = count
    data['rating'] = rating
    return data


class ReplyPreviewSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sender = serializers.CharField(source='sender.username')
    preview = serializers.SerializerMethodField()

    def get_preview(self, obj):
        return obj.preview_text()


def _item_data(item, request):
    if item is None:
        return None
    return {
        'id': item.pk,
        'name': getattr(item, 'name', ''),
        'photo': absolute_url(getattr(item, 'photo', None), request),
    }


class SwapCardSerializer(serializers.Serializer):
    """Read-only summary of the SwapRequest attached to a swap message."""
    id = serializers.IntegerField()
    status = serializers.CharField()
    status_label = serializers.SerializerMethodField()
    requester = serializers.CharField(source='sender.username')
    requested_item = serializers.SerializerMethodField()
    offered_item = serializers.SerializerMethodField()
    top_up_summary = serializers.SerializerMethodField()
    cancellation_requested_by = serializers.SerializerMethodField()

    def get_status_label(self, obj):
        return obj.get_status_display()

    def get_requested_item(self, obj):
        return _item_data(obj.requested_item, self.context.get('request'))

    def get_offered_item(self, obj):
        return _item_data(obj.offered_item, self.context.get('request'))

    def get_top_up_summary(self, obj):
        value = obj.top_up_summary
        value = value() if callable(value) else value
        return str(value) if value else ''

    def get_cancellation_requested_by(self, obj):
        user = getattr(obj, 'cancellation_requested_by', None)
        return user.username if user else None


class MessageSerializer(serializers.ModelSerializer):
    sender = UserMiniSerializer(read_only=True)
    reply_to = ReplyPreviewSerializer(read_only=True)
    swap_request = serializers.PrimaryKeyRelatedField(read_only=True)
    swap_card = serializers.SerializerMethodField()
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
            'reply_to', 'swap_request', 'swap_card',
        ]

    def get_attachment_url(self, obj):
        if obj.message_type not in (Message.MessageType.IMAGE, Message.MessageType.FILE):
            return None
        path = reverse('chat:attachment', args=[obj.pk])
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request else path

    def get_swap_card(self, obj):
        if obj.swap_request_id is None or obj.swap_request is None:
            return None
        return SwapCardSerializer(obj.swap_request, context=self.context).data


class ConversationItemSerializer(serializers.Serializer):
    """Wraps the dicts returned by _conversation_items() in chat/views.py."""
    id = serializers.IntegerField(source='conversation.id')
    other = UserMiniSerializer()
    item_id = serializers.IntegerField(source='conversation.item_id', allow_null=True)
    item_name = serializers.CharField(source='conversation.item_name')
    accepted = serializers.BooleanField(source='conversation.accepted')
    is_request = serializers.SerializerMethodField()
    preview = serializers.CharField()
    last_time = serializers.DateTimeField()
    unread = serializers.IntegerField()

    def get_is_request(self, obj):
        conv = obj['conversation']
        request = self.context.get('request')
        return bool(request) and not conv.accepted and conv.user2_id == request.user.pk