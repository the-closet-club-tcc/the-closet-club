from django import forms

from closet.models import Clothing
from .models import OutfitPost

MAX_IMAGE_MB = 5


class OutfitPostForm(forms.ModelForm):
    class Meta:
        model = OutfitPost
        fields = ['image', 'caption', 'clothes']
        widgets = {
            'image': forms.FileInput(attrs={'accept': 'image/*'}),
            'caption': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Tell us about this outfit...'}),
            'clothes': forms.CheckboxSelectMultiple,
        }
        labels = {'image': 'Outfit photo', 'clothes': 'Tag items from your closet'}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Users can only tag clothes that are in their own closet
        qs = Clothing.objects.filter(owner=user) if user else Clothing.objects.none()
        field = self.fields['clothes']
        field.queryset = qs
        field.required = False
        field.label_from_instance = (
            lambda c: f'{c.name} · {c.get_size_display()} · {c.get_status_display()}'
        )

    def clean_image(self):
        image = self.cleaned_data['image']
        if image.size > MAX_IMAGE_MB * 1024 * 1024:
            raise forms.ValidationError(f'Image must be under {MAX_IMAGE_MB} MB.')
        return image