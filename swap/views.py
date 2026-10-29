from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from django.utils import timezone

from closet.models import Clothing
from chat.models import Conversation
from chat.services import ensure_swap_card, post_swap_update, users_blocked
from accounts.forms import ReviewForm
from accounts.models import Review

from .forms import CounterOfferForm
from .models import Interest, SwapRequest, SwapReview
from .availability import ACTIVE_STATUSES, RESERVED_STATUSES, SWAP_STATUSES, available_swap_items, reserved_item_ids


def _request_counts(user):
    incoming = SwapRequest.objects.filter(recipient=user, status=SwapRequest.Status.PENDING).count()
    outgoing = SwapRequest.objects.filter(sender=user, status=SwapRequest.Status.COUNTERED).count()
    return {
        'pending_incoming_count': incoming,
        'pending_outgoing_count': outgoing,
        'pending_request_count': incoming + outgoing,
    }


@transaction.atomic
def _send_request(user, item_id):
    item = Clothing.objects.select_for_update().filter(pk=item_id).exclude(owner=user).first()
    if item is None or item.status not in SWAP_STATUSES:
        raise ValueError('This item is no longer available for swap.')
    if users_blocked(user.pk, item.owner_id):
        raise PermissionDenied('Swaps are unavailable between blocked users.')
    existing = SwapRequest.objects.filter(
        sender=user, requested_item=item, status__in=ACTIVE_STATUSES,
    ).first()
    if existing:
        Interest.objects.get_or_create(user=user, item=item)
        _sync_swap_chat(existing)
        return existing, False
    if not available_swap_items().filter(pk=item.pk).exists():
        raise ValueError('This item is already reserved for another swap.')
    proposal = SwapRequest.objects.create(sender=user, recipient=item.owner, requested_item=item)
    Interest.objects.get_or_create(user=user, item=item)
    _sync_swap_chat(proposal)
    return proposal, True

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
        **_request_counts(request.user),
    })


@login_required(login_url='login')
@never_cache
def interested_items(request):
    interests = Interest.objects.filter(user=request.user).select_related('item__owner')
    pending_item_ids = set(SwapRequest.objects.filter(
        sender=request.user, status__in=ACTIVE_STATUSES,
    ).values_list('requested_item_id', flat=True))
    reserved_ids = set(reserved_item_ids())
    for interest in interests:
        interest.request_pending = interest.item_id in pending_item_ids
        interest.reserved = interest.item_id in reserved_ids
        interest.available = (
            interest.item.status in SWAP_STATUSES
            and interest.item.owner_id != request.user.pk
        )
    return render(request, 'swap/interested.html', {
        'interests': interests, **_request_counts(request.user),
    })

def _get_or_create_conversation(user_a_id, user_b_id):
    list(get_user_model().objects.select_for_update().filter(pk__in=[user_a_id, user_b_id]).order_by('pk'))
    conversation = Conversation.objects.filter(
        Q(user1_id=user_a_id, user2_id=user_b_id)
        | Q(user1_id=user_b_id, user2_id=user_a_id)
    ).first()
    if conversation is None:
        conversation = Conversation.objects.create(user1_id=user_a_id, user2_id=user_b_id)
    return conversation


@transaction.atomic
def _sync_swap_chat(proposal, actor=None, text=None):
    if users_blocked(proposal.sender_id, proposal.recipient_id):
        return None
    conversation = _get_or_create_conversation(proposal.sender_id, proposal.recipient_id)
    card = ensure_swap_card(conversation, proposal)
    conversation = card.conversation
    if text:
        post_swap_update(conversation, actor, f'Swap #{proposal.pk}: {text}')
        conversation.save(update_fields=['updated_at'])
    return conversation


@require_POST
def save_interest(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Please sign in to save an item.'}, status=401)
    try:
        proposal, created = _send_request(request.user, pk)
    except PermissionDenied as error:
        return JsonResponse({'error': str(error)}, status=403)
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=404)
    return JsonResponse({'saved': True, 'request_id': proposal.pk, 'created': created})


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
        status__in=ACTIVE_STATUSES,
    ).select_related('requested_item').first()
    if existing_request:
        if request.method == 'POST':
            return _open_proposal_chat(existing_request)
        messages.info(request, 'You already have an active request for this piece.')
        return redirect('swap:requests_outgoing')

    error = None
    if request.method == 'POST':
        try:
            _send_request(request.user, item.pk)
        except ValueError as exception:
            error = str(exception)
        else:
            messages.success(request, 'Swap request sent. The owner can now choose a piece from your closet.')
            return redirect('swap:requests_outgoing')
    return render(request, 'swap/start_request.html', {
        'item': item, 'available': available, 'error': error, **_request_counts(request.user),
    }, status=400 if error else 200)


@login_required(login_url='login')
@never_cache
@require_http_methods(['GET', 'POST'])
def counter_offer(request, pk):
    proposal = get_object_or_404(
        SwapRequest.objects.select_related('sender', 'recipient', 'requested_item'),
        pk=pk, recipient=request.user,
    )
    if users_blocked(proposal.sender_id, proposal.recipient_id):
        raise PermissionDenied('Swaps are unavailable between blocked users.')
    if proposal.status != SwapRequest.Status.PENDING:
        messages.info(request, 'This request has already been updated. Your existing offer has not changed.')
        return redirect('swap:requests_incoming')
    item = proposal.requested_item
    available = bool(item and item.owner_id == request.user.pk and available_swap_items().filter(pk=item.pk).exists())
    form = CounterOfferForm(request.POST if request.method == 'POST' else None, proposal=proposal)
    if request.method == 'POST':
        valid = form.is_valid()
        if not available:
            form.add_error(None, 'Your requested piece is no longer available for swap.')
        elif valid:
            offered_item = form.cleaned_data['offered_item']
            with transaction.atomic():
                locked_items = {
                    piece.pk: piece for piece in Clothing.objects.select_for_update().filter(
                        pk__in=[item.pk, offered_item.pk],
                    ).order_by('pk')
                }
                proposal = get_object_or_404(
                    SwapRequest.objects.select_for_update(), pk=pk, recipient=request.user,
                )
                if proposal.status != SwapRequest.Status.PENDING:
                    messages.info(request, 'This request has already been updated. Your existing offer has not changed.')
                    return redirect('swap:requests_incoming')
                target = locked_items.get(item.pk)
                offered = locked_items.get(offered_item.pk)
                if not target or target.pk != proposal.requested_item_id or target.status not in SWAP_STATUSES or target.owner_id != request.user.pk:
                    available = False
                    form.add_error(None, 'This piece is no longer available for swap.')
                elif not offered or offered.status not in SWAP_STATUSES or offered.owner_id != proposal.sender_id:
                    form.add_error('offered_item', 'This piece is no longer available. Choose another item.')
                elif form.cleaned_data['top_up_payer'] != SwapRequest.TopUpPayer.NONE and Clothing.Status.TOP_UP not in (target.status, offered.status):
                    form.add_error('top_up_payer', 'Neither piece allows top-up anymore. Choose No top-up or another piece.')
                elif SwapRequest.objects.filter(status__in=RESERVED_STATUSES).filter(
                    Q(offered_item_id__in=locked_items) | Q(requested_item_id__in=locked_items),
                ).exists():
                    form.add_error(None, 'One of these pieces is already in a swap. Please choose another offer.')
                else:
                    proposal.offered_item = offered
                    proposal.top_up_payer = form.cleaned_data['top_up_payer']
                    proposal.top_up_amount = form.cleaned_data['top_up_amount']
                    proposal.status = SwapRequest.Status.COUNTERED
                    proposal.countered_at = timezone.now()
                    proposal.status_changed_at = proposal.countered_at
                    proposal.save(update_fields=[
                        'offered_item', 'top_up_payer', 'top_up_amount', 'status', 'countered_at', 'status_changed_at',
                    ])
                    _sync_swap_chat(
                        proposal, request.user,
                        f'{request.user.username} proposed {offered.name} in exchange for {target.name}. '
                        f'{proposal.top_up_summary} Review the counter-offer in Swap > Swap requests > Outgoing.',
                    )
                    messages.success(request, 'Counter-offer sent. The requester must accept before either piece is reserved.')
                    return redirect('swap:requests_incoming')

    return render(request, 'swap/propose.html', {
        'item': item, 'proposal': proposal, 'available': available, 'form': form,
        'offer_items': form.fields['offered_item'].queryset,
        'has_offers': form.fields['offered_item'].queryset.exists(),
        **_request_counts(request.user),
    }, status=400 if request.method == 'POST' else 200)


def _open_proposal_chat(proposal):
    conversation = _sync_swap_chat(proposal)
    if conversation is None:
        raise PermissionDenied('Chat is unavailable between blocked users.')
    item = proposal.requested_item
    if item and item.owner_id == proposal.recipient_id and item.status in SWAP_STATUSES:
        conversation.item_id = item.pk
        conversation.item_name = item.name[:150]
        conversation.save(update_fields=['item_id', 'item_name'])
    return redirect('chat:room', conversation_id=conversation.pk)


@login_required(login_url='login')
@require_POST
@transaction.atomic
def open_request_chat(request, pk):
    proposal = get_object_or_404(
        SwapRequest.objects.select_for_update().filter(Q(sender=request.user) | Q(recipient=request.user)),
        pk=pk,
    )
    return _open_proposal_chat(proposal)


@login_required(login_url='login')
@never_cache
@require_http_methods(['GET', 'POST'])
def review_swap(request, pk):
    with transaction.atomic():
        proposal = get_object_or_404(
            SwapRequest.objects.select_for_update().filter(Q(sender=request.user) | Q(recipient=request.user)),
            pk=pk,
        )
        if proposal.status != SwapRequest.Status.COMPLETED:
            raise PermissionDenied('Reviews are available only after both people complete the swap.')
        partner = proposal.recipient if proposal.sender_id == request.user.pk else proposal.sender
        destination = 'swap:requests_outgoing' if proposal.sender_id == request.user.pk else 'swap:requests_incoming'
        if SwapReview.objects.filter(swap_request=proposal, reviewer=request.user).exists():
            messages.info(request, 'You have already reviewed this swap.')
            return redirect(destination)
        review = Review(pemberi_review=request.user, penerima_review=partner)
        form = ReviewForm(request.POST if request.method == 'POST' else None, instance=review)
        if request.method == 'POST' and form.is_valid():
            review = form.save()
            SwapReview.objects.create(swap_request=proposal, reviewer=request.user, review=review)
            messages.success(request, 'Your review is now visible on their profile. Thank you!')
            return redirect(destination)
    return render(request, 'swap/review.html', {
        'proposal': proposal, 'partner': partner, 'form': form, 'destination': destination,
        **_request_counts(request.user),
    }, status=400 if request.method == 'POST' else 200)


@login_required(login_url='login')
@never_cache
def swap_requests(request, direction='incoming'):
    is_incoming = direction == 'incoming'
    requests = SwapRequest.objects.filter(
        **({'recipient': request.user} if is_incoming else {'sender': request.user}),
    ).select_related('sender', 'recipient', 'offered_item', 'requested_item')
    accepted_items = set(reserved_item_ids())
    reviewed_ids = set(SwapReview.objects.filter(reviewer=request.user).values_list('swap_request_id', flat=True))
    for swap_request in requests:
        swap_request.you_reviewed = swap_request.pk in reviewed_ids
        swap_request.partner = swap_request.sender if is_incoming else swap_request.recipient
        swap_request.you_confirmed = bool(
            swap_request.sender_confirmed_at if swap_request.sender_id == request.user.pk
            else swap_request.recipient_confirmed_at
        )
        swap_request.you_requested_cancellation = swap_request.cancellation_requested_by_id == request.user.pk
        swap_request.has_accepted_conflict = (
            swap_request.status in (SwapRequest.Status.PENDING, SwapRequest.Status.COUNTERED)
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
        **_request_counts(request.user),
    })


@login_required(login_url='login')
@require_POST
def update_request_status(request, pk, action):
    statuses = {
        'accept': SwapRequest.Status.ACCEPTED,
        'decline': SwapRequest.Status.DECLINED,
        'cancel': SwapRequest.Status.CANCELLED,
    }
    if action not in (*statuses, 'start', 'complete', 'keep'):
        return HttpResponseBadRequest('Unknown request action.')
    participants = Q(sender=request.user) | Q(recipient=request.user)
    proposal = get_object_or_404(SwapRequest.objects.filter(participants), pk=pk)
    if action in ('accept', 'start') and users_blocked(proposal.sender_id, proposal.recipient_id):
        raise PermissionDenied('Swaps are unavailable between blocked users.')
    destination = 'swap:requests_outgoing' if proposal.sender_id == request.user.pk else 'swap:requests_incoming'

    with transaction.atomic():
        items = {
            item.pk: item for item in Clothing.objects.select_for_update().filter(
                pk__in=[item_id for item_id in (proposal.offered_item_id, proposal.requested_item_id) if item_id is not None],
            ).order_by('pk')
        }
        proposal = get_object_or_404(SwapRequest.objects.select_for_update().filter(participants), pk=pk)
        decision_user_id = proposal.sender_id if proposal.status == SwapRequest.Status.COUNTERED else proposal.recipient_id
        if action in ('accept', 'decline') and decision_user_id != request.user.pk:
            raise Http404
        if action == 'cancel' and proposal.status == SwapRequest.Status.PENDING and proposal.sender_id != request.user.pk:
            raise Http404
        allowed = (
            proposal.status == SwapRequest.Status.PENDING and (
                action in ('decline', 'cancel') or action == 'accept' and proposal.offered_item_id is not None
            )
            or proposal.status == SwapRequest.Status.COUNTERED and action in statuses
            or proposal.status == SwapRequest.Status.ACCEPTED and action in ('start', 'cancel', 'keep')
            or proposal.status == SwapRequest.Status.IN_PROGRESS and action in ('cancel', 'complete', 'keep')
        )
        if not allowed:
            messages.info(request, 'This request has already been updated. Please check its current status.')
            return redirect(destination)

        if action == 'keep':
            had_cancellation = proposal.cancellation_requested_by_id is not None
            proposal.cancellation_requested_by = None
            proposal.cancellation_requested_at = None
            proposal.save(update_fields=['cancellation_requested_by', 'cancellation_requested_at'])
            if had_cancellation:
                _sync_swap_chat(proposal, request.user, f'{request.user.username} dismissed the cancellation. The exchange can continue.')
            messages.info(request, 'Cancellation dismissed. The swap can continue.')
            return redirect(destination)

        if action == 'cancel' and proposal.status in RESERVED_STATUSES:
            if proposal.cancellation_requested_by_id is None:
                proposal.cancellation_requested_by = request.user
                proposal.cancellation_requested_at = timezone.now()
                proposal.save(update_fields=['cancellation_requested_by', 'cancellation_requested_at'])
                _sync_swap_chat(proposal, request.user, f'{request.user.username} requested cancellation. Review it in Swap > Swap requests.')
                messages.info(request, 'Cancellation requested. The other person needs to agree before the pieces are released.')
                return redirect(destination)
            if proposal.cancellation_requested_by_id == request.user.pk:
                messages.info(request, 'Waiting for the other person to agree to cancellation.')
                return redirect(destination)

        if action in ('accept', 'start', 'complete'):
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
            if SwapRequest.objects.filter(status__in=RESERVED_STATUSES).exclude(pk=proposal.pk).filter(
                Q(offered_item_id__in=items) | Q(requested_item_id__in=items),
            ).exists():
                messages.error(request, 'One of these pieces already belongs to an accepted swap request.')
                return redirect(destination)

        if action == 'start':
            proposal.status = SwapRequest.Status.IN_PROGRESS
            proposal.status_changed_at = timezone.now()
            proposal.save(update_fields=['status', 'status_changed_at'])
            _sync_swap_chat(proposal, request.user, 'Exchange started. Both people must confirm receipt in Swap > Swap requests when finished.')
            messages.success(request, 'Exchange started. Both people must confirm once the exchange is finished.')
            return redirect(destination)

        if action == 'complete':
            field = 'sender_confirmed_at' if proposal.sender_id == request.user.pk else 'recipient_confirmed_at'
            if getattr(proposal, field) is None:
                setattr(proposal, field, timezone.now())
                proposal.save(update_fields=[field])
                _sync_swap_chat(proposal, request.user, f'{request.user.username} confirmed receipt of their piece.')
            if not (proposal.sender_confirmed_at and proposal.recipient_confirmed_at):
                messages.info(request, 'Your completion is confirmed. Waiting for the other person.')
                return redirect(destination)
            now = timezone.now()
            Clothing.objects.filter(pk__in=items).update(status=Clothing.Status.SWAPPED, updated_at=now)
            proposal.status = SwapRequest.Status.COMPLETED
            proposal.status_changed_at = now
            proposal.save(update_fields=['status', 'status_changed_at'])
            competing = SwapRequest.objects.select_for_update().filter(status__in=(SwapRequest.Status.PENDING, SwapRequest.Status.COUNTERED)).filter(
                Q(offered_item_id__in=items) | Q(requested_item_id__in=items),
            )
            for other in competing:
                other.status = SwapRequest.Status.CANCELLED
                other.status_changed_at = now
                other.save(update_fields=['status', 'status_changed_at'])
                if request.user.pk in (other.sender_id, other.recipient_id):
                    _sync_swap_chat(other, request.user, 'Request cancelled because a piece was exchanged in another swap.')
            _sync_swap_chat(proposal, request.user, 'Swap completed by both people. You can now leave a review in Swap > Swap requests.')
            messages.success(request, 'Swap completed by both people. Both pieces are now marked Already swapped.')
            return redirect(destination)

        proposal.status = statuses[action]
        proposal.status_changed_at = timezone.now()
        proposal.save(update_fields=['status', 'status_changed_at'])
        _sync_swap_chat(
            proposal, request.user,
            f'{request.user.username} {proposal.get_status_display().lower()} the swap. '
            'See the current details in Swap > Swap requests.',
        )
    messages.success(request, f'Swap request {proposal.get_status_display().lower()}.')
    return redirect(destination)
