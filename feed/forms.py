from django import forms

from closet.models import Clothes
from .models import OutfitPost

MAX_IMAGE_MB = 5


class OutfitPostForm(forms.ModelForm):
    class Meta:
        model = OutfitPost
        fields = ['image', 'caption', 'clothes']
        widgets = {
            'caption': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Tell us about this outfit...'}),
            'clothes': forms.CheckboxSelectMultiple,
        }
        labels = {'image': 'Outfit photo', 'clothes': 'Tag items from your closet'}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Users can only tag clothes that are in their own closet
        qs = Clothes.objects.filter(owner=user) if user else Clothes.objects.none()
        self.fields['clothes'].queryset = qs
        self.fields['clothes'].required = False

    def clean_image(self):
        image = self.cleaned_data['image']
        if image.size > MAX_IMAGE_MB * 1024 * 1024:
            raise forms.ValidationError(f'Image must be under {MAX_IMAGE_MB} MB.')
        return image