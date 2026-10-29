"""Aturan "terkunci" untuk pakaian yang sedang/sudah dipakai dalam swap.

Sumber kebenaran reservasi ada di modul Swap (swap/availability.py). Import-nya
dilakukan di dalam fungsi supaya tidak terjadi circular import saat app dimuat.
"""
from .models import Clothing

SWAPPED_REASON = 'Already swapped'
RESERVED_REASON = 'In an active swap'


def reserved_ids():
    """ID pakaian yang direservasi oleh swap berstatus accepted / in progress."""
    from swap.availability import reserved_item_ids
    return set(reserved_item_ids())


def lock_reason(item, reserved=None):
    """Alasan item tidak boleh dihapus / diubah statusnya. String kosong = tidak terkunci."""
    if item.status == Clothing.Status.SWAPPED:
        return SWAPPED_REASON
    if reserved is None:
        reserved = reserved_ids()
    if item.pk in reserved:
        return RESERVED_REASON
    return ''


def is_swappable(item, reserved=None):
    """True kalau item boleh diminta lewat Interested (aturan yang sama dengan Swap)."""
    from swap.availability import SWAP_STATUSES
    if item.status not in SWAP_STATUSES:
        return False
    if reserved is None:
        reserved = reserved_ids()
    return item.pk not in reserved
