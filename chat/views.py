from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from decimal import Decimal, InvalidOperation
from django.http import HttpResponseBadRequest
from .osm import search_places
from .models import Conversation, Message


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

    new_users = None
    if request.GET.get('new'):
        q = request.GET.get('q', '').strip()
        qs = get_user_model().objects.exclude(pk=user.pk)
        if q:
            qs = qs.filter(username__icontains=q)
        new_users = qs.order_by('username')[:50]    

    return render(request, 'chat/index.html', {
        'conversations': items,
        'active': active,
        'other_user': active.other_user(user) if active else None,
        'chat_messages': chat_messages,
        'new_users': new_users,
    })

def _get_conversation(user, conversation_id):
    """Percakapan hanya bisa diakses peserta. Selain itu 404."""
    qs = Conversation.objects.filter(Q(user1=user) | Q(user2=user))
    return get_object_or_404(qs, pk=conversation_id)


def _render_messages(request, conversation):
    conversation.messages.filter(is_read=False).exclude(
        sender=request.user
    ).update(is_read=True)
    return render(request, 'chat/_messages.html', {
        'chat_messages': conversation.messages.select_related('sender'),
    })


@login_required
def messages_partial(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    return _render_messages(request, conv)


@login_required
@require_POST
def send_message(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    content = request.POST.get('content', '').strip()[:2000]
    if content:
        Message.objects.create(
            conversation=conv, sender=request.user, content=content,
        )
        conv.save(update_fields=['updated_at'])
    return _render_messages(request, conv)


@login_required
@require_http_methods(['GET', 'POST'])
def edit_message(request, message_id):
    # Hanya pengirim yang boleh edit pesan teks miliknya sendiri
    msg = get_object_or_404(
        Message, pk=message_id, sender=request.user, message_type='text',
    )
    conv = _get_conversation(request.user, msg.conversation_id)
    if request.method == 'POST':
        content = request.POST.get('content', '').strip()[:2000]
        if content and content != msg.content:
            msg.content = content
            msg.is_edited = True
            msg.save()
        return _render_messages(request, conv)
    return render(request, 'chat/_edit_form.html', {'m': msg})


@login_required
@require_POST
def delete_message(request, message_id):
    msg = get_object_or_404(Message, pk=message_id, sender=request.user)
    conv = _get_conversation(request.user, msg.conversation_id)
    msg.delete()
    return _render_messages(request, conv)

@login_required
@require_POST
def start_conversation(request, user_id):
    other = get_object_or_404(get_user_model(), pk=user_id)
    if other == request.user:
        return redirect('chat:index')
    conv = Conversation.objects.filter(
        Q(user1=request.user, user2=other) | Q(user1=other, user2=request.user)
    ).first()
    if conv is None:
        conv = Conversation.objects.create(user1=request.user, user2=other)
    item_id = request.POST.get('item_id', '')
    if item_id.isdigit():
        conv.item_id = int(item_id)
        conv.item_name = request.POST.get('item_name', '')[:150]
        conv.save()
    return redirect('chat:room', conversation_id=conv.id)

@login_required
def place_search(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    q = request.GET.get('q', '').strip()[:100]
    category = request.GET.get('category', '')
    results = search_places(q, category) if q else []
    return render(request, 'chat/_place_results.html', {
        'results': results, 'conversation': conv, 'searched': bool(q),
    })


@login_required
@require_POST
def send_location(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    try:
        lat = Decimal(request.POST.get('lat', '')).quantize(Decimal('0.000001'))
        lon = Decimal(request.POST.get('lon', '')).quantize(Decimal('0.000001'))
    except (InvalidOperation, ValueError):
        return HttpResponseBadRequest('Koordinat tidak valid')
    if not (lat.is_finite() and lon.is_finite()
            and -90 <= lat <= 90 and -180 <= lon <= 180):
        return HttpResponseBadRequest('Koordinat tidak valid')
    name = request.POST.get('name', '').strip()[:150]
    if not name:
        return HttpResponseBadRequest('Nama tempat wajib diisi')
    Message.objects.create(
        conversation=conv, sender=request.user, message_type='location',
        place_name=name, address=request.POST.get('address', '').strip()[:255],
        latitude=lat, longitude=lon,
    )
    conv.save(update_fields=['updated_at'])
    return _render_messages(request, conv)