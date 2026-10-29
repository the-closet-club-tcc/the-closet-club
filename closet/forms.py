from django import forms
from django.core.files.uploadedfile import UploadedFile

from .models import Clothing, delete_stored_file

MAX_PHOTO_MB = 5


class ClothingForm(forms.ModelForm):
    class Meta:
        model = Clothing
        fields = ['photo', 'name', 'size', 'condition', 'status', 'description']
        labels = {
            'photo': 'Photo',
            'name': 'Item name',
            'status': 'Availability',
        }
        widgets = {
            'photo': forms.FileInput(attrs={'accept': 'image/*'}),
            'name': forms.TextInput(attrs={
                'class': 'closet-input', 'placeholder': 'e.g. Vintage Denim Jacket',
            }),
            'size': forms.Select(attrs={'class': 'closet-input'}),
            'condition': forms.Select(attrs={'class': 'closet-input'}),
            'status': forms.Select(attrs={'class': 'closet-input'}),
            'description': forms.Textarea(attrs={
                'class': 'closet-input', 'rows': 5,
                'placeholder': 'Brand, material, fit, flaws, what you would like in return...',
            }),
        }

    def __init__(self, *args, status_locked=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Simpan nama foto lama untuk dihapus kalau foto diganti
        self._old_photo = (
            self.instance.photo.name if self.instance.pk and self.instance.photo else None
        )
        # "Already swapped" hanya diatur oleh modul Swap, jadi tidak bisa dipilih manual
        if self.instance.status != Clothing.Status.SWAPPED:
            self.fields['status'].choices = [
                c for c in self.fields['status'].choices
                if c[0] != Clothing.Status.SWAPPED
            ]
        if status_locked:
            # Item sedang dalam swap / sudah ditukar: status tidak boleh diubah dari Closet
            self.fields['status'].disabled = True
            self.fields['status'].help_text = (
                'Availability is locked while this item is in a swap or already swapped.'
            )
        self.fields['photo'].help_text = f'JPG, PNG, or WEBP. Max {MAX_PHOTO_MB} MB.'

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        # Hanya cek ukuran untuk file yang baru diunggah
        if isinstance(photo, UploadedFile) and photo.size > MAX_PHOTO_MB * 1024 * 1024:
            raise forms.ValidationError(f'Photo must be {MAX_PHOTO_MB} MB or smaller.')
        return photo

    def save(self, commit=True):
        obj = super().save(commit=commit)
        if commit and self._old_photo and self._old_photo != obj.photo.name:
            delete_stored_file(obj.photo.storage, self._old_photo)
        return obj
