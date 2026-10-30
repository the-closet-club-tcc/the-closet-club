from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.forms import AuthenticationForm
from datetime import timedelta
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from .forms import (
    CustomUserCreationForm,
    DeleteAccountConfirmationForm,
    EditProfileForm,
    ReviewForm,
)
from .models import Review, Verification
from swap.models import SwapRequest

User = get_user_model()


def _reviewable_swap(giver, receiver):
    if not giver.is_authenticated or giver.pk == receiver.pk:
        return None
    return SwapRequest.objects.filter(
        status=SwapRequest.Status.COMPLETED,
    ).filter(
        Q(sender=giver, recipient=receiver) | Q(sender=receiver, recipient=giver),
    ).exclude(
        reviews__pemberi_review=giver,
    ).order_by('-status_changed_at', '-pk').first()


def _get_profile_reviews(request, user_profile):
    reviews = user_profile.reviews_received.select_related("pemberi_review").order_by("-tanggal", "-pk")
    start_value = request.GET.get("start_date", "")
    end_value = request.GET.get("end_date", "")
    start_date = parse_date(start_value) if start_value else None
    end_date = parse_date(end_value) if end_value else None
    filter_error = ""

    if start_value and start_date is None or end_value and end_date is None:
        filter_error = "Please enter valid start and end dates."
    elif start_date and end_date and start_date > end_date:
        filter_error = "The start date must be on or before the end date."
    else:
        if start_date:
            reviews = reviews.filter(tanggal__date__gte=start_date)
        if end_date:
            reviews = reviews.filter(tanggal__date__lte=end_date)

    now = timezone.now()
    reviews = list(reviews)
    for review in reviews:
        review.can_edit = (
            request.user.is_authenticated
            and review.pemberi_review_id == request.user.pk
            and review.tanggal <= now <= review.tanggal + timedelta(hours=24)
        )

    return reviews, start_value, end_value, filter_error


def register(request):
    form = CustomUserCreationForm(
        request.POST or None,
        request.FILES or None
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your account has been created. Please sign in.")
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

        response = redirect("profile")

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
    response = redirect("profile")
    # Hapus cookie
    response.delete_cookie("last_login")
    return response


@login_required(login_url="login")
def profile(request):
    user = request.user
    reviews, review_start_date, review_end_date, review_filter_error = _get_profile_reviews(request, user)

    context = {
        "closet_items": user.clothes.all(),
        "user_profile": user,
        "reviews": reviews,
        "can_review": False,
        "review_start_date": review_start_date,
        "review_end_date": review_end_date,
        "review_filter_error": review_filter_error,
    }

    return render(request, "accounts/profile.html", context)


@login_required(login_url="login")
@transaction.atomic
def edit_profile(request):
    if request.method == "POST":
        user = User.objects.select_for_update().get(pk=request.user.pk)
        form = EditProfileForm(
            request.POST,
            request.FILES,
            instance=user
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("profile")

    else:
        form = EditProfileForm(instance=request.user)

    context = {
        "form": form
    }

    return render(request, "accounts/edit_profile.html", context)


@login_required(login_url="login")
def delete_account(request):
    if request.method == "POST":
        form = DeleteAccountConfirmationForm(request.POST, user=request.user)
        if form.is_valid():
            user = request.user
            logout(request)
            user.delete()
            messages.success(request, "Your account has been deleted.")
            return redirect("home")
    else:
        form = DeleteAccountConfirmationForm(user=request.user)

    return render(request, "accounts/delete_account.html", {"form": form})

def public_profile(request, username):
    user_profile = get_object_or_404(User, username=username)
    reviewable_swap = _reviewable_swap(request.user, user_profile)
    reviews, review_start_date, review_end_date, review_filter_error = _get_profile_reviews(request, user_profile)
    context={
        "user_profile": user_profile,
        "closet_items": user_profile.clothes.all(),
        "reviews": reviews,
        "can_review": reviewable_swap is not None,
        "review_start_date": review_start_date,
        "review_end_date": review_end_date,
        "review_filter_error": review_filter_error,
    }
    return render(request, "accounts/profile.html", context)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def request_verification(request):
    wants_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
    user = User.objects.select_for_update().get(pk=request.user.pk)
    if user.is_verified:
        if wants_json:
            return JsonResponse({"success": True, "status": "verified", "message": "Your account is already verified."})
        messages.info(request, "Your account is already verified.")
        return redirect("profile")

    try:
        user.validate_verification_details()
    except ValidationError:
        if wants_json:
            return JsonResponse({
                "success": False,
                "message": "Please enter your first name, last name, and a valid email address before requesting verification.",
                "redirect_url": reverse("edit_profile"),
            }, status=400)
        messages.error(
            request,
            "Please enter your first name, last name, and a valid email address before requesting verification."
        )
        return redirect("edit_profile")
    verification, created = Verification.objects.get_or_create(
        user=user
    )

    if created:
        message = "Your verification request has been submitted."
        message_level = "success"
    elif verification.status == "rejected":
        verification.status = "pending"
        verification.save(update_fields=["status"])
        message = "Your verification request has been resubmitted."
        message_level = "success"
    else:
        message = "Your verification request has already been submitted."
        message_level = "info"
    if wants_json:
        return JsonResponse({"success": True, "status": verification.status, "message": message})
    getattr(messages, message_level)(request, message)
    return redirect("profile")

@login_required(login_url="login")
@require_POST
@transaction.atomic
def add_review(request, username):
    wants_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
    penerima = get_object_or_404(
        User,
        username=username
    )

    if request.user.pk == penerima.pk:
        if wants_json:
            return JsonResponse({"success": False, "message": "You cannot review your own account."}, status=400)
        messages.error(request, "You cannot review your own account.")
        return redirect("profile")

    swap_request = _reviewable_swap(request.user, penerima)
    if swap_request is None:
        if wants_json:
            return JsonResponse({"success": False, "message": "You can submit only one review for each completed swap."}, status=400)
        messages.error(request, "You can submit only one review for each completed swap.")
        return redirect("public_profile", username=penerima.username)

    form = ReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.pemberi_review = request.user
        review.penerima_review = penerima
        review.swap_request = swap_request
        review.save()
        if wants_json:
            review_count = penerima.reviews_received.count()
            return JsonResponse({
                "success": True,
                "message": "Your review has been submitted.",
                "review": {
                    "id": review.pk,
                    "username": request.user.username,
                    "rating": str(review.rating),
                    "comment": review.komentar or "",
                    "date": timezone.localtime(review.tanggal).strftime("%d %B %Y"),
                    "date_iso": timezone.localtime(review.tanggal).date().isoformat(),
                    "edit_url": reverse("edit_review", kwargs={"review_id": review.pk}),
                    "average": penerima.get_rata_rata_rating(),
                    "count": review_count,
                },
            })
        messages.success(request, "Your review has been submitted.")
    else:
        if wants_json:
            return JsonResponse({"success": False, "message": "Please choose a valid rating and try again."}, status=400)
        messages.error(request, "Invalid rating. Please try again.")
    return redirect("public_profile", username=penerima.username)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def edit_review(request, review_id):
    review = get_object_or_404(
        Review.objects.select_for_update().select_related("penerima_review"),
        pk=review_id,
        pemberi_review=request.user,
    )
    profile_url = reverse("public_profile", kwargs={"username": review.penerima_review.username})
    now = timezone.now()

    if now < review.tanggal or now > review.tanggal + timedelta(hours=24):
        messages.error(request, "Reviews can only be edited within 24 hours of submission.")
        return redirect(profile_url)

    form = ReviewForm(request.POST, instance=review)
    if form.is_valid():
        form.save()
        messages.success(request, "Your review has been updated.")
    else:
        messages.error(request, "Please choose a valid rating and try again.")

    return redirect(profile_url)
