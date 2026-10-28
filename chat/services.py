from django.db.models import Q

from .models import Block, Message


def ensure_swap_card(conversation, swap_request):
    """Ensure a SwapRequest has exactly one linked card message.

    Safe to call repeatedly (room open, polling, and retries) without creating
    duplicate messages for the same SwapRequest.
    """
    msg, created = Message.objects.get_or_create(
        swap_request=swap_request,
        message_type=Message.MessageType.SWAP,
        defaults={
            'conversation': conversation,
            'sender_id': swap_request.sender_id,
            'content': f'{swap_request.sender.username} wants to swap with you!',
        },
    )
    if created:
        conversation.save(update_fields=['updated_at'])
    return msg


def sync_swap_cards(conversation):
    """Backfill missing swap cards for every request between room participants."""
    # Import here to keep Chat's model initialization independent from Swap.
    from swap.models import SwapRequest

    pair = (
        Q(sender_id=conversation.user1_id, recipient_id=conversation.user2_id)
        | Q(sender_id=conversation.user2_id, recipient_id=conversation.user1_id)
    )
    requests = list(
        SwapRequest.objects.filter(pair).select_related('sender').order_by('created_at', 'pk')
    )
    if not requests:
        return 0

    request_ids = [swap_request.pk for swap_request in requests]
    existing_ids = set(Message.objects.filter(
        message_type=Message.MessageType.SWAP,
        swap_request_id__in=request_ids,
    ).values_list('swap_request_id', flat=True))
    for swap_request in requests:
        ensure_swap_card(conversation, swap_request)
    return len(set(request_ids) - existing_ids)


def post_swap_update(conversation, actor, text):
    message = Message.objects.create(
        conversation=conversation,
        sender=actor,
        message_type=Message.MessageType.TEXT,
        content=text,
    )
    conversation.save(update_fields=['updated_at'])
    return message


def users_blocked(user_a_id, user_b_id):
    return Block.objects.filter(
        Q(blocker_id=user_a_id, blocked_id=user_b_id)
        | Q(blocker_id=user_b_id, blocked_id=user_a_id)
    ).exists()


_SWAP_EVENT_TEXTS = {
    'request_accepted': 'Penawaran swap disetujui. Kalian bisa melanjutkan pertukaran barang.',
    'request_declined': 'Permintaan swap ditolak.',
    'request_cancelled': 'Permintaan swap dibatalkan.',
    'cancellation_requested': 'Meminta pembatalan swap. Menunggu persetujuan pihak lain.',
    'cancellation_approved': 'Pembatalan swap disetujui oleh kedua pihak.',
    'cancellation_dismissed': 'Permintaan pembatalan ditolak. Swap dapat dilanjutkan.',
    'exchange_started': 'Pertukaran dimulai. Setelah barang ditukar, kedua pihak perlu mengonfirmasi penyelesaian.',
    'completion_confirmed': 'Satu pihak telah mengonfirmasi penyelesaian swap. Menunggu konfirmasi pihak lain.',
    'swap_completed': 'Swap selesai. Kedua barang telah ditandai sudah ditukar.',
}


def swap_event_text(event):
    """Human-readable Chat update for a meaningful Swap state change."""
    return _SWAP_EVENT_TEXTS.get(event)
