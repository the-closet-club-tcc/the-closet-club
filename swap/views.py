from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from django.utils import timezone

from closet.models import Clothing
from chat.models import Conversation

from .forms import SwapRequestForm
from .models import Interest, SwapRequest
from .availability import SWAP_STATUSES, available_swap_items, reserved_item_ids


@login_required(login_url='login')
@never_cache
def swap_page(request):
    current_status = request.GET.get('status', '')
    if current_status not in SWAP_STATUSES:
        current_status = ''

    items = available_swap_items().select_related('owner')
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
        sender=request.user, status__in=(SwapRequest.Status.PENDING, SwapRequest.Status.ACCEPTED),
    ).values_list('requested_item_id', flat=True))
    reserved_ids = set(reserved_item_ids())
    for interest in interests:
        interest.request_pending = interest.item_id in pending_item_ids
        interest.reserved = interest.item_id in reserved_ids
        interest.available = (
            interest.item.status in SWAP_STATUSES
            and interest.item.owner_id != request.user.pk
        )
    return render(request, 'swap/interested.html', {'interests': interests})


@require_POST
def save_interest(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Please sign in to save an item.'}, status=401)
    item = available_swap_items().exclude(owner=request.user).filter(pk=pk).first()
    if item is None:
        return JsonResponse({'error': 'This item is no longer available for swap.'}, status=404)
    Interest.objects.get_or_create(user=request.user, item=item)
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
    available = available_swap_items().exclude(owner=request.user).filter(pk=item.pk).exists()
    existing_request = SwapRequest.objects.filter(
        sender=request.user, requested_item=item,
        status__in=(SwapRequest.Status.PENDING, SwapRequest.Status.ACCEPTED),
    ).select_related('requested_item').first()
    if existing_request:
        if request.method == 'POST':
            return _open_proposal_chat(existing_request)
        messages.info(request, 'You already have an active request for this piece.')
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
                elif SwapRequest.objects.filter(status=SwapRequest.Status.ACCEPTED).filter(
                    Q(offered_item_id__in=locked_items) | Q(requested_item_id__in=locked_items),
                ).exists():
                    form.add_error(None, 'One of these pieces is already in a swap. Please choose another offer.')
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
    accepted_items = set(reserved_item_ids())
    for swap_request in requests:
        swap_request.you_confirmed = bool(
            swap_request.sender_confirmed_at if swap_request.sender_id == request.user.pk
            else swap_request.recipient_confirmed_at
        )
        swap_request.you_requested_cancellation = swap_request.cancellation_requested_by_id == request.user.pk
        swap_request.has_accepted_conflict = (
            swap_request.status == SwapRequest.Status.PENDING
            and bool({swap_request.offered_item_id, swap_request.requested_item_id} & accepted_items)
        )
        visible_statuses = (*SWAP_STATUSES, Clothing.Status.SWAPPED) if swap_request.status == SwapRequest.Status.COMPLETED else SWAP_STATUSES
        swap_request.offered_available = (
            swap_request.offered_item is not None
            and swap_request.offered_item.status in visible_statuses
            and swap_request.offered_item.owner_id == swap_request.sender_id
        )
        swap_request.requested_available = (
            swap_request.requested_item is not None
            and swap_request.requested_item.status in visible_statuses
            and swap_request.requested_item.owner_id == swap_request.recipient_id
        )
    return render(request, 'swap/requests.html', {
        'swap_requests': requests, 'is_incoming': is_incoming,
    })


@login_required(login_url='login')
@require_POST
def update_request_status(request, pk, action):
    statuses = {
        'accept': SwapRequest.Status.ACCEPTED,
        'decline': SwapRequest.Status.DECLINED,
        'cancel': SwapRequest.Status.CANCELLED,
    }
    if action not in (*statuses, 'complete', 'keep'):
        return HttpResponseBadRequest('Unknown request action.')
    participants = Q(sender=request.user) | Q(recipient=request.user)
    proposal = get_object_or_404(SwapRequest.objects.filter(participants), pk=pk)
    destination = 'swap:requests_outgoing' if proposal.sender_id == request.user.pk else 'swap:requests_incoming'

    with transaction.atomic():
        items = {
            item.pk: item for item in Clothing.objects.select_for_update().filter(
                pk__in=[item_id for item_id in (proposal.offered_item_id, proposal.requested_item_id) if item_id is not None],
            ).order_by('pk')
        }
        proposal = get_object_or_404(SwapRequest.objects.select_for_update().filter(participants), pk=pk)
        if action in ('accept', 'decline') and proposal.recipient_id != request.user.pk:
            raise Http404
        if action == 'cancel' and proposal.status == SwapRequest.Status.PENDING and proposal.sender_id != request.user.pk:
            raise Http404
        allowed = (
            proposal.status == SwapRequest.Status.PENDING and action in statuses
            or proposal.status == SwapRequest.Status.ACCEPTED and action in ('cancel', 'complete', 'keep')
        )
        if not allowed:
            messages.info(request, 'This request has already been updated. Please check its current status.')
            return redirect(destination)

        if action == 'keep':
            proposal.cancellation_requested_by = None
            proposal.cancellation_requested_at = None
            proposal.save(update_fields=['cancellation_requested_by', 'cancellation_requested_at'])
            messages.info(request, 'Cancellation dismissed. This swap is still accepted.')
            return redirect(destination)

        if action == 'cancel' and proposal.status == SwapRequest.Status.ACCEPTED:
            if proposal.cancellation_requested_by_id is None:
                proposal.cancellation_requested_by = request.user
                proposal.cancellation_requested_at = timezone.now()
                proposal.save(update_fields=['cancellation_requested_by', 'cancellation_requested_at'])
                messages.info(request, 'Cancellation requested. The other person needs to agree before the pieces are released.')
                return redirect(destination)
            if proposal.cancellation_requested_by_id == request.user.pk:
                messages.info(request, 'Waiting for the other person to agree to cancellation.')
                return redirect(destination)

        if action in ('accept', 'complete'):
            if proposal.cancellation_requested_by_id is not None:
                messages.error(request, 'Resolve the cancellation request before confirming completion.')
                return redirect(destination)
            offered = items.get(proposal.offered_item_id)
            requested = items.get(proposal.requested_item_id)
            if (
                not offered or not requested
                or offered.owner_id != proposal.sender_id
                or requested.owner_id != proposal.recipient_id
                or offered.status not in SWAP_STATUSES
                or requested.status not in SWAP_STATUSES
            ):
                messages.error(request, 'This action cannot continue because a piece is unavailable or its owner has changed.')
                return redirect(destination)
            if SwapRequest.objects.filter(status=SwapRequest.Status.ACCEPTED).exclude(pk=proposal.pk).filter(
                Q(offered_item_id__in=items) | Q(requested_item_id__in=items),
            ).exists():
                messages.error(request, 'One of these pieces already belongs to an accepted swap request.')
                return redirect(destination)

        if action == 'complete':
            field = 'sender_confirmed_at' if proposal.sender_id == request.user.pk else 'recipient_confirmed_at'
            if getattr(proposal, field) is None:
                setattr(proposal, field, timezone.now())
                proposal.save(update_fields=[field])
            if not (proposal.sender_confirmed_at and proposal.recipient_confirmed_at):
                messages.info(request, 'Your completion is confirmed. Waiting for the other person.')
                return redirect(destination)
            now = timezone.now()
            Clothing.objects.filter(pk__in=items).update(status=Clothing.Status.SWAPPED, updated_at=now)
            proposal.status = SwapRequest.Status.COMPLETED
            proposal.status_changed_at = now
            proposal.save(update_fields=['status', 'status_changed_at'])
            SwapRequest.objects.filter(status=SwapRequest.Status.PENDING).filter(
                Q(offered_item_id__in=items) | Q(requested_item_id__in=items),
            ).update(status=SwapRequest.Status.CANCELLED, status_changed_at=now)
            messages.success(request, 'Swap completed by both people. Both pieces are now marked Already swapped.')
            return redirect(destination)

        proposal.status = statuses[action]
        proposal.status_changed_at = timezone.now()
        proposal.save(update_fields=['status', 'status_changed_at'])
    messages.success(request, f'Swap request {proposal.get_status_display().lower()}.')
    return redirect(destination)
