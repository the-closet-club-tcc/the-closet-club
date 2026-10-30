from django.db import models, router, transaction
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.contrib.auth.models import AbstractUser
from django.db.models import Avg
from django.core.validators import MinValueValidator, MaxValueValidator

# Create your models here.
class User(AbstractUser):
    foto_profil = models.ImageField(upload_to='profile_pics/', null = True, blank = True)
    is_verified = models.BooleanField(default=False)
    bio = models.TextField(blank=True)
    lokasi = models.CharField(max_length=100, blank=True)
    def validate_verification_details(self):
        errors = {}
        for name in ("first_name", "last_name"):
            if not getattr(self, name).strip():
                errors[name] = "First and last name are required."
        try:
            validate_email(self.email.strip())
        except ValidationError:
            errors["email"] = "A valid email address is required."
        if errors:
            raise ValidationError(errors)

    def get_rata_rata_rating(self):
        rata_rata = self.reviews_received.aggregate(Avg('rating'))['rating__avg']
        return round(rata_rata, 1) if rata_rata is not None else 0.0

    def __str__(self):
        return self.username
    
class Verification(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='verification')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    tanggal_pengajuan = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.pk:
            previous_user_id = type(self).objects.filter(pk=self.pk).values_list(
                "user_id", flat=True,
            ).first()
            if previous_user_id is not None and previous_user_id != self.user_id:
                raise ValidationError({"user": "The request owner cannot be changed."})
        if self.status == "approved" and self.user_id:
            try:
                self.user.validate_verification_details()
            except ValidationError as error:
                raise ValidationError(error.messages)

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            # Gunakan data identitas terbaru saat memproses keputusan admin.
            self.user = User.objects.using(using).select_for_update().get(pk=self.user_id)
            self.full_clean()
            result = super().save(*args, **kwargs)
            status = type(self).objects.using(using).values_list(
                "status", flat=True,
            ).get(pk=self.pk)
            self.user.is_verified = status == "approved"
            User.objects.using(using).filter(pk=self.user_id).update(
                is_verified=self.user.is_verified,
            )
            return result


@receiver(post_delete, sender=Verification)
def revoke_deleted_verification(sender, instance, using, **kwargs):
    # post_delete juga berjalan untuk penghapusan massal dari Django Admin.
    User.objects.using(using).filter(pk=instance.user_id).update(is_verified=False)


class Review(models.Model):
    pemberi_review = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_given')
    penerima_review = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_received')  
    swap_request = models.ForeignKey(
        'swap.SwapRequest', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviews',
    )
    rating = models.DecimalField(max_digits=2, decimal_places=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    komentar = models.TextField(blank=True, null=True)
    tanggal = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['swap_request', 'pemberi_review'],
                name='unique_review_per_swap_and_giver',
            ),
        ]

    def clean(self):
        super().clean()
        if self.pemberi_review_id and self.pemberi_review_id == self.penerima_review_id:
            raise ValidationError("You cannot review your own account.")
        if self.swap_request_id:
            from swap.models import SwapRequest

            swap_request = self.swap_request
            participants_match = (
                swap_request.sender_id == self.pemberi_review_id
                and swap_request.recipient_id == self.penerima_review_id
            ) or (
                swap_request.recipient_id == self.pemberi_review_id
                and swap_request.sender_id == self.penerima_review_id
            )
            if swap_request.status != SwapRequest.Status.COMPLETED:
                raise ValidationError({"swap_request": "A review can only be submitted after the swap is completed."})
            if not participants_match:
                raise ValidationError({"swap_request": "Only participants in the swap can submit a review."})

    def save(self, *args, **kwargs):
        # Simpan hanya review yang terikat ke swap selesai milik kedua peserta.
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Review by {self.pemberi_review.username} for {self.penerima_review.username} ({self.rating}/5)"
