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
    class TopUpPayer(models.TextChoices):
        NONE = 'none', 'No top-up'
        SENDER = 'sender', 'I pay the top-up'
        RECIPIENT = 'recipient', 'The other person pays the top-up'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COUNTERED = 'countered', 'Counter offered'
        ACCEPTED = 'accepted', 'Accepted'
        IN_PROGRESS = 'in_progress', 'In progress'
        DECLINED = 'declined', 'Declined'
        CANCELLED = 'cancelled', 'Cancelled'
        COMPLETED = 'completed', 'Completed'

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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    countered_at = models.DateTimeField(null=True, blank=True)
    sender_confirmed_at = models.DateTimeField(null=True, blank=True)
    recipient_confirmed_at = models.DateTimeField(null=True, blank=True)
    cancellation_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='swap_cancellation_requests',
    )
    cancellation_requested_at = models.DateTimeField(null=True, blank=True)
    top_up_payer = models.CharField(max_length=9, choices=TopUpPayer.choices, default=TopUpPayer.NONE)
    top_up_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)

    @property
    def top_up_summary(self):
        if self.top_up_payer == self.TopUpPayer.NONE:
            return 'No top-up. Pieces only.'
        payer, payee = (self.sender, self.recipient) if self.top_up_payer == self.TopUpPayer.SENDER else (self.recipient, self.sender)
        amount = format(self.top_up_amount, ',.0f').replace(',', '.')
        return f'{payer.username} pays Rp {amount} to {payee.username}.'

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(top_up_payer='none', top_up_amount__isnull=True)
                    | models.Q(top_up_payer__in=['sender', 'recipient'], top_up_amount__isnull=False, top_up_amount__gt=0)
                ),
                name='swap_valid_top_up_terms',
            ),
            models.UniqueConstraint(
                fields=['sender', 'requested_item'],
                condition=models.Q(status__in=['pending', 'countered', 'accepted', 'in_progress']),
                name='unique_active_swap_request',
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


class SwapReview(models.Model):
    swap_request = models.ForeignKey(SwapRequest, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='swap_reviews')
    review = models.OneToOneField(
        'accounts.Review', on_delete=models.SET_NULL, null=True, related_name='swap_review',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['swap_request', 'reviewer'], name='unique_review_per_swap_user'),
        ]
