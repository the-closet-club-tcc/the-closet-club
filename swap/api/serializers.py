from rest_framework import serializers
from swap.models import SwapRequest


class SwapRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = SwapRequest
        fields = [
            'id',
            'sender',
            'recipient',
            'offered_item',
            'requested_item',
            'status',
            'created_at',
            'top_up_payer',
            'top_up_amount',
        ]
        read_only_fields = fields