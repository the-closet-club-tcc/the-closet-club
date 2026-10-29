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
    'request_accepted': 'Swap agreed. Complete the exchange before leaving a review.',
    'request_declined': 'Swap request declined.',
    'request_cancelled': 'Swap request cancelled.',
    'cancellation_requested': 'Cancellation requested. Waiting for the other person to agree.',
    'cancellation_approved': 'Swap cancelled by both people.',
    'cancellation_dismissed': 'Cancellation declined. The swap can continue.',
    'exchange_started': 'Exchange started. Both people must confirm once the exchange is finished.',
    'completion_confirmed': 'One person confirmed the exchange. Waiting for the other person.',
    'swap_completed': 'Swap completed.',
}


def swap_event_text(event):
    """Human-readable Chat update for a meaningful Swap state change."""
    return _SWAP_EVENT_TEXTS.get(event)
