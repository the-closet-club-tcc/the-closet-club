from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, EditProfileForm
from .models import Verification

User = get_user_model()

def register(request):
    form = CustomUserCreationForm(
        request.POST or None,
        request.FILES or None
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Akun berhasil dibuat! Silakan login.")
        return redirect("login")

    context = {
        "form": form
    }
    return render(request, "accounts/register.html", context)


def login_user(request):
    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.get_user()

        login(request, user)

        # Catat waktu login
        waktu_login = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")

        response = redirect("home")

        # Simpan waktu login dalam cookie
        response.set_cookie(
            "last_login",
            waktu_login,
            httponly=True,
            samesite="Lax"
        )
        return response

    context = {
        "form": form
    }
    return render(request, "accounts/login.html", context)


@require_POST
def logout_view(request):
    logout(request)
    response = redirect("home")
    # Hapus cookie
    response.delete_cookie("last_login")
    return response


@login_required(login_url="login")
def profile(request):
    user = request.user

    context = {
        "user_profile": user
    }

    return render(request, "accounts/profile.html", context)


@login_required(login_url="login")
def edit_profile(request):
    if request.method == "POST":
        form = EditProfileForm(
            request.POST,
            request.FILES,
            instance=request.user
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Profil berhasil diperbarui!")
            return redirect("profile")

    else:
        form = EditProfileForm(instance=request.user)

    context = {
        "form": form
    }

    return render(request, "accounts/edit_profile.html", context)

def public_profile(request, username):
    user_profile = get_object_or_404(User, username=username)
    context={
        "user_profile": user_profile
    }
    return render(request, "accounts/profile.html", context)


@login_required(login_url="login")
@require_POST
def request_verification(request):
    user = request.user
    if user.is_verified:
        messages.info(request, "Akun kamu sudah terverifikasi.")
        return redirect("profile")

    if (
        not user.first_name.strip()
        or not user.last_name.strip()
        or not user.email.strip()
    ):
        messages.error(
            request,
            "Lengkapi nama depan, nama belakang, dan email terlebih dahulu."
        )
        return redirect("edit_profile")
    verification, created = Verification.objects.get_or_create(
        user=user
    )

    if created:
        messages.success(
            request,
            "Pengajuan verifikasi berhasil dikirim."
        )
    elif verification.status == "rejected":
        verification.status = "pending"
        verification.save(update_fields=["status"])
        messages.success(
            request,
            "Pengajuan verifikasi berhasil dikirim ulang."
        )
    else:
        messages.info(
            request,
            "Pengajuan verifikasi kamu sudah tercatat."
        )
    return redirect("profile")
