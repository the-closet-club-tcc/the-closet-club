from django.conf import settings
from django.db import models


class Interest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='swap_interests',
    )
    item = models.ForeignKey(
        'closet.Clothing', on_delete=models.CASCADE, related_name='swap_interests',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['user', 'item'], name='unique_swap_interest'),
        ]


class SwapRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='sent_swap_requests',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='received_swap_requests',
    )
    offered_item = models.ForeignKey(
        'closet.Clothing', on_delete=models.SET_NULL, null=True,
        related_name='outgoing_swap_requests',
    )
    requested_item = models.ForeignKey(
        'closet.Clothing', on_delete=models.SET_NULL, null=True,
        related_name='incoming_swap_requests',
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['sender', 'requested_item'], condition=models.Q(status='pending'),
                name='unique_pending_swap_request',
            ),
            models.CheckConstraint(
                condition=~models.Q(sender=models.F('recipient')),
                name='swap_request_different_users',
            ),
            models.CheckConstraint(
                condition=~models.Q(offered_item=models.F('requested_item')),
                name='swap_request_different_items',
            ),
        ]
