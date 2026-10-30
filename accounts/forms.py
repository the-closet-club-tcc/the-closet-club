
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Review
from decimal import Decimal


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "foto_profil"]

class EditProfileForm(forms.ModelForm):
    email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.is_verified:
            for name in ("first_name", "last_name", "email"):
                self.fields[name].disabled = True
                self.fields[name].help_text = (
                    "This information is locked while your account is verified."
                )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "bio",
            "lokasi",
            "foto_profil"
        ]

        widgets = {
            "foto_profil": forms.FileInput(
                attrs={"accept": "image/*"}
            )
        }


class ReviewForm(forms.ModelForm):
    # rating 1 sampai 5 bintang
    rating = forms.TypedChoiceField(
        choices=[
            ("1", "★☆☆☆☆"),
            ("2", "★★☆☆☆"),
            ("3", "★★★☆☆"),
            ("4", "★★★★☆"),
            ("5", "★★★★★"),
        ],
        coerce=Decimal,
        widget=forms.RadioSelect,
        label="Rating"
    )

    class Meta:
        model = Review
        fields = [
            "rating",
            "komentar"
        ]

        widgets = {
            "komentar": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Tell us about your swap experience..."
                }
            )
        }
