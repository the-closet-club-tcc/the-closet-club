from django import forms

from closet.models import Clothing


class SwapRequestForm(forms.Form):
    offered_item = forms.ModelChoiceField(
        queryset=Clothing.objects.none(),
        empty_label='Choose a piece from your closet',
        label='Your offer',
        error_messages={'invalid_choice': 'Choose an available piece from your own closet.'},
        widget=forms.Select(attrs={'aria-describedby': 'offer-help offer-errors'}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['offered_item'].queryset = Clothing.objects.filter(
            owner=user, status__in=(Clothing.Status.BARTER, Clothing.Status.TOP_UP),
        )
        self.fields['offered_item'].label_from_instance = (
            lambda item: f'{item.name} — {item.get_size_display()} · {item.get_status_display()}'
        )
