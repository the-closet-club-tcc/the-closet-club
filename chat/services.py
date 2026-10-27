from .models import Message


def ensure_swap_card(conversation, swap_request):
    """Pastikan percakapan punya tepat satu kartu untuk SwapRequest ini.

    Aman dipanggil berulang (refresh, klik ganda): kartu tidak akan dobel.
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