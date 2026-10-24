import io
import mimetypes
import os
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse, HttpResponseBadRequest
from django.core.exceptions import SuspiciousFileOperation
from django.db import transaction
from django.utils.http import content_disposition_header
from django.utils.text import get_valid_filename
from PIL import Image, ImageOps

from .osm import search_places
from .models import Attachment, Conversation, Message


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
        elif last.message_type == 'image':
            preview = 'Foto'
        elif last.message_type == 'file':
            preview = f'Dokumen: {last.attachment_name}'
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
        'max_image_bytes': MAX_UPLOAD,
        'max_doc_bytes': MAX_UPLOAD,        
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

MAX_UPLOAD = 10 * 1024 * 1024
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
DOC_EXTS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'}

def _normalize_image(data):
    """Validasi gambar, perkecil, simpan sebagai JPEG (EXIF ikut terhapus)."""
    Image.open(io.BytesIO(data)).verify()
    img = Image.open(io.BytesIO(data))
    if img.format not in {'JPEG', 'PNG', 'WEBP', 'GIF'}:
        raise ValueError('format tidak didukung')
    if img.format == 'JPEG':
        img.draft('RGB', (2560, 2560))    
    img = ImageOps.exif_transpose(img).convert('RGB')
    img.thumbnail((1280, 1280))
    out = io.BytesIO()
    img.save(out, 'JPEG', quality=85)
    return out.getvalue()

@login_required
@require_POST
def send_attachment(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    upload = request.FILES.get('file')
    if upload is None:
        return HttpResponseBadRequest('Pilih file dulu')
    try:
        name = get_valid_filename(os.path.basename(upload.name))[:255]
    except SuspiciousFileOperation:
        return HttpResponseBadRequest('Nama file tidak valid')

    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXTS:
        kind, limit = Message.MessageType.IMAGE, MAX_UPLOAD
    elif ext in DOC_EXTS:
        kind, limit = Message.MessageType.FILE, MAX_UPLOAD
    else:
        return HttpResponseBadRequest('Tipe file tidak didukung')
    if upload.size > limit:
        return HttpResponseBadRequest(f'Ukuran file maksimal {limit // (1024 * 1024)} MB')

    data = upload.read()
    if kind == Message.MessageType.IMAGE:
        try:
            data = _normalize_image(data)
        except Exception:
            return HttpResponseBadRequest('File gambar tidak valid')
        ctype = 'image/jpeg'
        name = os.path.splitext(name)[0] + '.jpg'
    else:
        ctype = mimetypes.guess_type(name)[0] or 'application/octet-stream'

    with transaction.atomic():
        msg = Message.objects.create(
            conversation=conv, sender=request.user, message_type=kind,
            attachment_name=name, attachment_type=ctype, attachment_size=len(data),
        )
        Attachment.objects.create(message=msg, data=data)
    conv.save(update_fields=['updated_at'])
    return _render_messages(request, conv)

@login_required
def attachment(request, message_id):
    att = get_object_or_404(Attachment.objects.select_related('message'), message_id=message_id)
    msg = att.message
    _get_conversation(request.user, msg.conversation_id)  # non-peserta -> 404
    response = HttpResponse(bytes(att.data), content_type=msg.attachment_type)
    inline = msg.message_type == Message.MessageType.IMAGE
    response['Content-Disposition'] = content_disposition_header(not inline, msg.attachment_name)
    response['X-Content-Type-Options'] = 'nosniff'
    return response