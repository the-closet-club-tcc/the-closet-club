from django.conf import settings
from django.db import models
from django.urls import reverse


class OutfitPost(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='outfit_posts',
    )
    image = models.ImageField(upload_to='outfits/%Y/%m/')
    caption = models.TextField(blank=True, max_length=500)
    # Items from the author's closet that are worn in this outfit
    clothes = models.ManyToManyField('closet.Clothing', blank=True, related_name='outfit_posts')
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='liked_posts')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'Outfit by {self.author} ({self.created_at:%Y-%m-%d})'

    def get_absolute_url(self):
        return reverse('feed:detail', kwargs={'pk': self.pk})