from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models import Avg

# Create your models here.
class User(AbstractUser):
    foto_profil = models.ImageField(upload_to='profile_pics/', null = True, blank = True)
    is_verified = models.BooleanField(default=False)

    def get_rata_rata_rating(self):
        rata_rata = self.reviews_received.aggregate(Avg('rating'))['rating__avg']
        return round(rata_rata, 1) if rata_rata is not None else 0.0

    def __str__(self):
        return self.username
class Verification(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Menunggu'),
        ('approved', 'Disetujui'),
        ('rejected', 'Ditolak'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='verification')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    tanggal_pengajuan = models.DateTimeField(auto_now_add=True)

class Review(models.Model):
    pemberi_review = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_given')
    penerima_review = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_received')
    
    rating = models.DecimalField(max_digits=2, decimal_places=1)
    komentar = models.TextField(blank=True, null=True)
    tanggal = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review dari {self.pemberi_review.username} ke {self.penerima_review.username} ({self.rating}/5)" 
