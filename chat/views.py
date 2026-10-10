from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Conversation


@login_required
def chat_index(request, conversation_id=None):
    user = request.user

    # Hanya percakapan yang melibatkan user ini
    base_qs = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user)
    ).select_related('user1', 'user2')

    active = None
    chat_messages = []
    if conversation_id is not None:
        # User yang bukan peserta otomatis dapat 404
        active = get_object_or_404(base_qs, pk=conversation_id)
        active.messages.filter(is_read=False).exclude(sender=user).update(is_read=True)
        chat_messages = active.messages.select_related('sender')

    items = []
    for conv in base_qs:
        last = conv.messages.order_by('-created_at').first()
        if last is None:
            preview = 'Belum ada pesan'
        elif last.message_type == 'location':
            preview = f'Lokasi: {last.place_name}'
        else:
            preview = last.content
        items.append({
            'conversation': conv,
            'other': conv.other_user(user),
            'preview': preview,
            'last_time': last.created_at if last else conv.created_at,
            'unread': conv.messages.filter(is_read=False).exclude(sender=user).count(),
        })

    return render(request, 'chat/index.html', {
        'conversations': items,
        'active': active,
        'other_user': active.other_user(user) if active else None,
        'chat_messages': chat_messages,
    })