from django import forms

from closet.models import Clothing

from .availability import available_swap_items
from .models import SwapRequest


class CounterOfferForm(forms.Form):
    offered_item = forms.ModelChoiceField(
        queryset=Clothing.objects.none(),
        empty_label="Choose a piece from the requester's closet",
        label='Piece you would like in return',
        error_messages={'invalid_choice': "Choose an available piece from the requester's closet."},
        widget=forms.Select(attrs={'aria-describedby': 'offer-help offer-errors'}),
    )

    top_up_payer = forms.ChoiceField(
        choices=SwapRequest.TopUpPayer.choices, required=False,
        initial=SwapRequest.TopUpPayer.NONE, label='Who pays the top-up?',
        widget=forms.Select(attrs={'aria-describedby': 'top-up-help top-up-payer-errors'}),
    )
    top_up_amount = forms.DecimalField(
        required=False, min_value=1, max_digits=12, decimal_places=0,
        label='Amount (IDR)',
        widget=forms.NumberInput(attrs={
            'min': '1', 'step': '1', 'placeholder': 'e.g. 50000',
            'aria-describedby': 'top-up-amount-help top-up-amount-errors',
        }),
    )

    def __init__(self, *args, proposal, **kwargs):
        super().__init__(*args, **kwargs)
        self.requested_item = proposal.requested_item
        self.fields['offered_item'].queryset = available_swap_items().filter(owner=proposal.sender)
        self.fields['top_up_payer'].choices = [
            (SwapRequest.TopUpPayer.NONE, 'No top-up'),
            (SwapRequest.TopUpPayer.SENDER, f'{proposal.sender.username} pays the top-up'),
            (SwapRequest.TopUpPayer.RECIPIENT, f'I ({proposal.recipient.username}) pay the top-up'),
        ]
        self.fields['offered_item'].label_from_instance = (
            lambda item: f'{item.name} — {item.get_size_display()} · {item.get_status_display()}'
        )

    def clean(self):
        cleaned = super().clean()
        payer = cleaned.get('top_up_payer') or SwapRequest.TopUpPayer.NONE
        cleaned['top_up_payer'] = payer
        amount = cleaned.get('top_up_amount')
        if payer == SwapRequest.TopUpPayer.NONE:
            if amount is not None:
                self.add_error('top_up_amount', 'Leave the amount empty for a swap without top-up.')
        else:
            if amount is None and 'top_up_amount' not in self.errors:
                self.add_error('top_up_amount', 'Enter the top-up amount in whole rupiah.')
            offered = cleaned.get('offered_item')
            if offered and self.requested_item and Clothing.Status.TOP_UP not in (
                offered.status, self.requested_item.status,
            ):
                self.add_error('top_up_payer', 'Top-up is only available when either piece is listed as Swap + top-up.')
        return cleaned
