import logging

from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse

logger = logging.getLogger(__name__)


def delete_stored_file(storage, name):
    """Hapus file foto dari storage setelah transaksi DB commit.

    Kegagalan storage (mis. Cloudinary tidak terjangkau) hanya dicatat di log
    dan tidak boleh menggagalkan request pengguna.
    """
    if not name:
        return

    def _delete():
        try:
            storage.delete(name)
        except Exception:
            logger.warning('Could not delete stored file %s', name, exc_info=True)

    transaction.on_commit(_delete)


class ClothingQuerySet(models.QuerySet):
    def offered(self):
        """Pakaian yang sedang ditawarkan ke user lain (tampil di katalog publik)."""
        return self.filter(status__in=Clothing.OFFER_STATUSES)


class Clothing(models.Model):
    class Size(models.TextChoices):
        XS = 'XS', 'XS'
        S = 'S', 'S'
        M = 'M', 'M'
        L = 'L', 'L'
        XL = 'XL', 'XL'
        XXL = 'XXL', 'XXL'
        ONE = 'ONE', 'One Size'

    class Condition(models.TextChoices):
        NEW = 'new', 'Brand New'
        VERY_GOOD = 'very_good', 'Very Good'
        GOOD = 'good', 'Good'
        FAIR = 'fair', 'Fair'

    class Status(models.TextChoices):
        PERSONAL = 'personal', 'Personal collection'
        BARTER = 'barter', 'Open to swap'
        TOP_UP = 'top_up', 'Swap + top-up'
        DONATE = 'donate', 'Free to a good home'
        SWAPPED = 'swapped', 'Already swapped'

    # Status yang dianggap "ditawarkan" ke user lain
    OFFER_STATUSES = (Status.BARTER, Status.TOP_UP, Status.DONATE)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='clothes',
    )
    name = models.CharField(max_length=100)
    photo = models.ImageField(upload_to='clothes/%Y/%m/')
    size = models.CharField(max_length=3, choices=Size.choices, default=Size.M)
    condition = models.CharField(
        max_length=10, choices=Condition.choices, default=Condition.GOOD,
    )
    description = models.TextField(blank=True, max_length=1000)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PERSONAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClothingQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name_plural = 'clothes'
        indexes = [models.Index(fields=['owner', 'status'])]

    @property
    def is_offered(self):
        return self.status in self.OFFER_STATUSES

    def get_absolute_url(self):
        return reverse('closet:item_detail', args=[self.pk])

    def __str__(self):
        return f'{self.name} ({self.owner})'


@receiver(post_delete, sender=Clothing)
def delete_photo_file(sender, instance, **kwargs):
    # Hapus file foto dari storage saat barisnya dihapus
    if instance.photo:
        delete_stored_file(instance.photo.storage, instance.photo.name)
