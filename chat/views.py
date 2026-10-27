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
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageOps

from .osm import search_places
from .models import Attachment, Block, Conversation, Message, Report
from .forms import ReportForm

def _get_conversation(user, conversation_id):
    """Percakapan hanya bisa diakses peserta. Selain itu 404."""
    qs = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user)
    ).select_related('user1', 'user2')
    return get_object_or_404(qs, pk=conversation_id)

def _blocked_state(user, other):
    """(saya memblokir dia, dia memblokir saya)."""
    mine = Block.objects.filter(blocker=user, blocked=other).exists()
    theirs = Block.objects.filter(blocker=other, blocked=user).exists()
    return mine, theirs


def _send_denied(user, conv):
    """Respons 403 kalau salah satu pihak memblokir, selain itu None."""
    mine, theirs = _blocked_state(user, conv.other_user(user))
    if mine:
        return HttpResponse('Buka blokir untuk mengirim pesan.', status=403)
    if theirs:
        return HttpResponse('Kamu tidak dapat mengirim pesan ke pengguna ini.', status=403)
    return None


def _mark_sent(conv, user):
    """Naikkan percakapan ke atas daftar. Balasan penerima otomatis menerima permintaan."""
    fields = ['updated_at']
    if not conv.accepted and user.pk == conv.user2_id:
        conv.accepted = True
        fields.append('accepted')
    conv.save(update_fields=fields)

def _recent_messages(conversation, user):
    """200 pesan terakhir yang masih terlihat oleh user, urut lama ke baru."""
    qs = conversation.visible_messages(user).select_related(
        'sender', 'reply_to', 'reply_to__sender',
    )    
    return list(reversed(qs.order_by('-created_at', '-id')[:MAX_MESSAGES]))


def _conversation_items(user, active_id=None):
    """Data daftar percakapan di kolom kiri (tanpa yang sudah dihapus user)."""
    convs = Conversation.objects.filter(
        Q(user1=user) | Q(user2=user)
    ).select_related('user1', 'user2')
    items = []
    for conv in convs:
        visible = conv.visible_messages(user)
        last = visible.order_by('-created_at', '-id').first()
        if last is None and conv.cleared_at_for(user):
            continue  # sudah dihapus dan belum ada pesan baru
        preview = last.preview_text() if last else 'Belum ada pesan'
        unread = 0 if conv.id == active_id else (
            visible.filter(is_read=False).exclude(sender=user).count()
        )
        items.append({
            'conversation': conv,
            'other': conv.other_user(user),
            'preview': preview,
            'last_time': last.created_at if last else conv.created_at,
            'unread': unread,
        })
    return items


def _render_messages(request, conversation):
    conversation.messages.filter(is_read=False).exclude(
        sender=request.user
    ).update(is_read=True)
    return render(request, 'chat/_messages.html', {
        'chat_messages': _recent_messages(conversation, request.user),
    })


@login_required
def chat_index(request, conversation_id=None):
    user = request.user
    active = None
    chat_messages = []
    if conversation_id is not None:
        active = _get_conversation(user, conversation_id)  # non-peserta -> 404
        active.messages.filter(is_read=False).exclude(sender=user).update(is_read=True)
        chat_messages = _recent_messages(active, user)

    blocked_by_me = blocked_me = is_request = False
    if active:
        blocked_by_me, blocked_me = _blocked_state(user, active.other_user(user))
        is_request = (not active.accepted) and user.pk == active.user2_id

    return render(request, 'chat/index.html', {
        'conversations': _conversation_items(user, active.id if active else None),
        'active': active,
        'active_id': active.id if active else None,
        'other_user': active.other_user(user) if active else None,
        'chat_messages': chat_messages,
        'max_image_bytes': MAX_UPLOAD,
        'max_doc_bytes': MAX_UPLOAD,
        'quick_replies': QUICK_REPLIES,
        'blocked_by_me': blocked_by_me,
        'blocked_me': blocked_me,
        'is_request': is_request,
        'report_reasons': Report.Reason.choices,        
    })

@login_required
def conversation_list(request):
    raw = request.GET.get('active', '')
    active_id = int(raw) if raw.isdigit() else None
    return render(request, 'chat/_conversation_list.html', {
        'conversations': _conversation_items(request.user, active_id),
        'active_id': active_id,
    })


@login_required
def user_search(request):
    q = request.GET.get('q', '').strip()[:50]
    blocked_ids = set(
        Block.objects.filter(blocker=request.user).values_list('blocked_id', flat=True)
    ) | set(
        Block.objects.filter(blocked=request.user).values_list('blocker_id', flat=True)
    )
    qs = get_user_model().objects.exclude(pk=request.user.pk).exclude(pk__in=blocked_ids)
    if q:
        qs = qs.filter(username__icontains=q)
    return render(request, 'chat/_user_results.html', {
        'new_users': qs.order_by('username')[:20], 'q': q,
    })


@login_required
@require_POST
def delete_conversation(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    now = timezone.now()
    if request.user.pk == conv.user1_id:
        conv.cleared_at_user1 = now
        conv.save(update_fields=['cleared_at_user1'])
    else:
        conv.cleared_at_user2 = now
        conv.save(update_fields=['cleared_at_user2'])
    return redirect(f"{reverse('chat:index')}?deleted=1")

@login_required
def messages_partial(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    return _render_messages(request, conv)

@login_required
@require_POST
def send_message(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    denied = _send_denied(request.user, conv)
    if denied:
        return denied
    content = request.POST.get('content', '').strip()[:2000]
    if content:
        reply_to = None
        raw = request.POST.get('reply_to', '')
        if raw.isdigit():
            # hanya pesan di percakapan ini yang masih terlihat oleh pengirim
            reply_to = conv.visible_messages(request.user).filter(pk=int(raw)).first()
        Message.objects.create(
            conversation=conv, sender=request.user, content=content,
            reply_to=reply_to, has_reply=reply_to is not None,
        )
        _mark_sent(conv, request.user)
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
    if any(_blocked_state(request.user, other)):
        return redirect(f"{reverse('chat:index')}?cannot_start=1")
    conv = Conversation.objects.filter(
        Q(user1=request.user, user2=other) | Q(user1=other, user2=request.user)
    ).first()
    if conv is None:
        conv = Conversation.objects.create(user1=request.user, user2=other, accepted=False)
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
    denied = _send_denied(request.user, conv)
    if denied:
        return denied    
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
    _mark_sent(conv, request.user)
    return _render_messages(request, conv)

MAX_UPLOAD = 10 * 1024 * 1024
MAX_MESSAGES = 200
QUICK_REPLIES = [
    'Masih tersedia?', 'Boleh nego?', 'Ukurannya muat?',
    'Bisa ketemu hari ini?', 'Terima kasih!',
]
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
    denied = _send_denied(request.user, conv)
    if denied:
        return denied    
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
    _mark_sent(conv, request.user)
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

@login_required
@require_POST
def block_user(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    Block.objects.get_or_create(blocker=request.user, blocked=conv.other_user(request.user))
    return redirect(f"{reverse('chat:room', args=[conv.id])}?blocked=1")

@login_required
@require_POST
def unblock_user(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    Block.objects.filter(blocker=request.user, blocked=conv.other_user(request.user)).delete()
    return redirect(f"{reverse('chat:room', args=[conv.id])}?unblocked=1")

@login_required
@require_POST
def report(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    other = conv.other_user(request.user)
    form = ReportForm(request.POST)
    if not form.is_valid():
        text = ' '.join(e for errs in form.errors.values() for e in errs)
        return HttpResponseBadRequest(text or 'Laporan tidak valid.')

    target = None
    raw = request.POST.get('message_id', '')
    if raw:
        if not raw.isdigit():
            return HttpResponseBadRequest('Pesan yang dilaporkan tidak ditemukan.')
        # hanya pesan lawan bicara di percakapan ini
        target = conv.visible_messages(request.user).filter(pk=int(raw), sender=other).first()
        if target is None:
            return HttpResponseBadRequest('Pesan yang dilaporkan tidak ditemukan.')

    obj = form.save(commit=False)
    obj.reporter = request.user
    obj.reported_user = other
    obj.message = target
    obj.message_excerpt = target.preview_text()[:300] if target else ''
    obj.save()
    return HttpResponse(status=204)


@login_required
@require_POST
def accept_conversation(request, conversation_id):
    conv = _get_conversation(request.user, conversation_id)
    room = reverse('chat:room', args=[conv.id])
    if request.user.pk == conv.user2_id and not conv.accepted:
        conv.accepted = True
        conv.save(update_fields=['accepted'])
        return redirect(f'{room}?accepted=1')
    return redirect(room)