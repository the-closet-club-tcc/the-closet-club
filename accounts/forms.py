
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


class DeleteAccountConfirmationForm(forms.Form):
    username = forms.CharField(label="Username", max_length=150)
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput,
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        password = cleaned_data.get("password")
        if username and password and (
            username != self.user.username or not self.user.check_password(password)
        ):
            raise forms.ValidationError(
                "Username atau password tidak sesuai dengan akun yang sedang login."
            )
        return cleaned_data


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
