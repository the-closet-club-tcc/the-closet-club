from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from closet.models import Clothing
from chat.models import Conversation
from chat.services import post_swap_request_card

from .forms import SwapRequestForm
from .models import Interest, SwapRequest

SWAP_STATUSES = (Clothing.Status.BARTER, Clothing.Status.TOP_UP)


@login_required(login_url='login')
@never_cache
def swap_page(request):
    current_status = request.GET.get('status', '')
    if current_status not in SWAP_STATUSES:
        current_status = ''

    items = Clothing.objects.filter(status__in=SWAP_STATUSES).select_related('owner')
    has_interests = False
    if request.user.is_authenticated:
        interests = Interest.objects.filter(user=request.user)
        has_interests = interests.exists()
        items = items.exclude(owner=request.user).exclude(
            pk__in=interests.values('item_id'),
        )
    if current_status:
        items = items.filter(status=current_status)

    filters = [
        {'value': '', 'label': 'All swap options'},
        {'value': Clothing.Status.BARTER, 'label': 'Swap only'},
        {'value': Clothing.Status.TOP_UP, 'label': 'Swap + top-up'},
    ]
    return render(request, 'swap.html', {
        'items': items,
        'filters': filters,
        'current_status': current_status,
        'has_interests': has_interests,
    })


@login_required(login_url='login')
@never_cache
def interested_items(request):
    interests = Interest.objects.filter(user=request.user).select_related('item__owner')
    pending_item_ids = set(SwapRequest.objects.filter(
        sender=request.user, status=SwapRequest.Status.PENDING,
    ).values_list('requested_item_id', flat=True))
    for interest in interests:
        interest.request_pending = interest.item_id in pending_item_ids
        interest.available = (
            interest.item.status in SWAP_STATUSES
            and interest.item.owner_id != request.user.pk
        )
    return render(request, 'swap/interested.html', {'interests': interests})


@require_POST
def save_interest(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Please sign in to save an item.'}, status=401)
    item = Clothing.objects.filter(pk=pk, status__in=SWAP_STATUSES).exclude(owner=request.user).first()
    if item is None:
        return JsonResponse({'error': 'This item is no longer available for swap.'}, status=404)
    Interest.objects.get_or_create(user=request.user, item=item)
    with transaction.atomic():
        swap_request, _ = SwapRequest.objects.get_or_create(
            sender=request.user, requested_item=item,
            status=SwapRequest.Status.PENDING,
            defaults={'recipient': item.owner},
        )
        post_swap_request_card(swap_request)
    return JsonResponse({'saved': True})


@login_required(login_url='login')
@require_POST
def remove_interest(request, pk):
    Interest.objects.filter(pk=pk, user=request.user).delete()
    return redirect('swap:interested')


@login_required(login_url='login')
@never_cache
@require_http_methods(['GET', 'POST'])
def propose_swap(request, pk):
    interest = get_object_or_404(
        Interest.objects.select_related('item__owner'), pk=pk, user=request.user,
    )
    item = interest.item
    available = item.status in SWAP_STATUSES and item.owner_id != request.user.pk
    existing_request = SwapRequest.objects.filter(
        sender=request.user, requested_item=item, status=SwapRequest.Status.PENDING,
    ).select_related('requested_item').first()
    if existing_request:
        if request.method == 'POST':
            return _open_proposal_chat(existing_request)
        messages.info(request, 'You already have a pending request for this piece.')
        return redirect('swap:requests_outgoing')

    form = SwapRequestForm(request.POST if request.method == 'POST' else None, user=request.user)
    if request.method == 'POST':
        if not available:
            form.add_error(None, 'This piece is no longer available for swap.')
        elif form.is_valid():
            offered_item = form.cleaned_data['offered_item']
            with transaction.atomic():
                locked_items = {
                    piece.pk: piece for piece in Clothing.objects.select_for_update().filter(
                        pk__in=[item.pk, offered_item.pk],
                    ).order_by('pk')
                }
                target = locked_items.get(item.pk)
                offered = locked_items.get(offered_item.pk)
                if not target or target.status not in SWAP_STATUSES or target.owner_id != item.owner_id:
                    available = False
                    form.add_error(None, 'This piece is no longer available for swap.')
                elif not offered or offered.status not in SWAP_STATUSES or offered.owner_id != request.user.pk:
                    form.add_error('offered_item', 'This piece is no longer available. Choose another item.')
                else:
                    proposal, _ = SwapRequest.objects.get_or_create(
                        sender=request.user, requested_item=target, status=SwapRequest.Status.PENDING,
                        defaults={'recipient': target.owner, 'offered_item': offered},
                    )
                    return _open_proposal_chat(proposal)

    return render(request, 'swap/propose.html', {
        'item': item, 'available': available, 'form': form,
        'has_offers': form.fields['offered_item'].queryset.exists(),
    }, status=400 if request.method == 'POST' else 200)


def _open_proposal_chat(proposal):
    conversation = Conversation.objects.filter(
        Q(user1_id=proposal.sender_id, user2_id=proposal.recipient_id)
        | Q(user1_id=proposal.recipient_id, user2_id=proposal.sender_id)
    ).first()
    if conversation is None:
        conversation = Conversation.objects.create(
            user1_id=proposal.sender_id, user2_id=proposal.recipient_id,
        )
    item = proposal.requested_item
    if item and item.status in SWAP_STATUSES and item.owner_id == proposal.recipient_id:
        conversation.item_id = item.pk
        conversation.item_name = item.name
        conversation.save(update_fields=['item_id', 'item_name', 'updated_at'])
    return redirect('chat:room', conversation_id=conversation.pk)


@login_required(login_url='login')
@never_cache
def swap_requests(request, direction='incoming'):
    is_incoming = direction == 'incoming'
    requests = SwapRequest.objects.filter(
        **({'recipient': request.user} if is_incoming else {'sender': request.user}),
    ).select_related('sender', 'recipient', 'offered_item', 'requested_item')
    for swap_request in requests:
        swap_request.offered_available = (
            swap_request.offered_item is not None
            and swap_request.offered_item.status in SWAP_STATUSES
            and swap_request.offered_item.owner_id == swap_request.sender_id
        )
        swap_request.requested_available = (
            swap_request.requested_item is not None
            and swap_request.requested_item.status in SWAP_STATUSES
            and swap_request.requested_item.owner_id == swap_request.recipient_id
        )
    return render(request, 'swap/requests.html', {
        'swap_requests': requests, 'is_incoming': is_incoming,
    })

S = SwapRequest.Status

def _back_to_chat(sr):
    conv = Conversation.objects.filter(
        Q(user1_id=sr.sender_id, user2_id=sr.recipient_id)
        | Q(user1_id=sr.recipient_id, user2_id=sr.sender_id)
    ).first()
    return redirect('chat:room', conversation_id=conv.pk) if conv else redirect('swap:requests_incoming')


def _lock(request, pk):
    sr = get_object_or_404(
        SwapRequest.objects.select_for_update(), pk=pk
    )
    if request.user.pk not in (sr.sender_id, sr.recipient_id):
        raise Http404
    return sr


@login_required(login_url='login')
@require_POST
def decline_swap(request, pk):
    with transaction.atomic():
        sr = _lock(request, pk)
        if sr.status in (S.PENDING, S.COUNTER_PROPOSED):
            sr.status = S.DECLINED
            sr.save(update_fields=['status'])
            messages.success(request, 'Swap request declined.')
    return _back_to_chat(sr)


@login_required(login_url='login')
@never_cache
@require_http_methods(['GET', 'POST'])
def choose_counter(request, pk):
    # Penerima memilih barang balasan dari closet pengirim
    sr = get_object_or_404(
        SwapRequest.objects.select_related('sender', 'requested_item'),
        pk=pk, recipient=request.user, status=S.PENDING,
    )
    choices = Clothing.objects.filter(owner=sr.sender, status__in=SWAP_STATUSES)
    if request.method == 'POST':
        with transaction.atomic():
            sr = SwapRequest.objects.select_for_update().get(pk=pk)
            picked = Clothing.objects.select_for_update().filter(
                pk=request.POST.get('offered_item'),
                owner_id=sr.sender_id, status__in=SWAP_STATUSES,
            ).first()
            if sr.status == S.PENDING and picked:
                sr.offered_item = picked
                sr.status = S.COUNTER_PROPOSED
                sr.save(update_fields=['offered_item', 'status'])
                messages.success(request, 'Counter offer sent.')
                return _back_to_chat(sr)
        messages.error(request, 'That piece is not available. Choose another.')
    return render(request, 'swap/choose_counter.html', {'swap_request': sr, 'choices': choices})


@login_required(login_url='login')
@require_POST
def agree_swap(request, pk):
    with transaction.atomic():
        sr = _lock(request, pk)
        if sr.status != S.COUNTER_PROPOSED or sr.sender_id != request.user.pk:
            raise Http404
        a, b = sr.requested_item, sr.offered_item
        pieces = list(Clothing.objects.select_for_update().filter(pk__in=[a.pk, b.pk]))
        if len(pieces) != 2 or any(p.status not in SWAP_STATUSES for p in pieces):
            messages.error(request, 'One of the pieces is no longer available.')
            return _back_to_chat(sr)
        sr.status = S.AGREED
        sr.save(update_fields=['status'])
        # BR-09: tolak request lain yang memakai barang yang sama
        SwapRequest.objects.exclude(pk=sr.pk).filter(
            status__in=[S.PENDING, S.COUNTER_PROPOSED],
        ).filter(
            Q(requested_item__in=[a, b]) | Q(offered_item__in=[a, b])
        ).update(status=S.DECLINED)
        messages.success(request, 'Swap agreed. Complete the exchange before leaving a review.')
    return _back_to_chat(sr)


@login_required(login_url='login')
@require_POST
def complete_swap(request, pk):
    with transaction.atomic():
        sr = _lock(request, pk)
        if sr.status != S.AGREED:
            raise Http404
        if request.user.pk == sr.sender_id:
            sr.sender_confirmed = True
        else:
            sr.recipient_confirmed = True
        if sr.sender_confirmed and sr.recipient_confirmed:
            sr.status = S.COMPLETED
            Clothing.objects.filter(
                pk__in=[sr.requested_item_id, sr.offered_item_id]
            ).update(status=Clothing.Status.SWAPPED)
            messages.success(request, 'Swap completed.')
        else:
            messages.success(request, 'Confirmed. Waiting for the other person.')
        sr.save()
    return _back_to_chat(sr)