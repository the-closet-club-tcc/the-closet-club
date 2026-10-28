from closet.models import Clothing

from .models import SwapRequest


SWAP_STATUSES = (Clothing.Status.BARTER, Clothing.Status.TOP_UP)


def reserved_item_ids():
    accepted = SwapRequest.objects.filter(status=SwapRequest.Status.ACCEPTED).order_by()
    return accepted.exclude(offered_item=None).values_list('offered_item_id', flat=True).union(
        accepted.exclude(requested_item=None).values_list('requested_item_id', flat=True),
    )


def available_swap_items():
    return Clothing.objects.filter(status__in=SWAP_STATUSES).exclude(pk__in=reserved_item_ids())
