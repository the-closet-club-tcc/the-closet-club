from django.conf import settings
from django.db import models


class Conversation(models.Model):
    user1 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='conversations_as_user1',
    )
    user2 = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='conversations_as_user2',
    )
    # Referensi item pakaian dibuat longgar supaya tidak bergantung ke modul Feed/Closet
    item_id = models.PositiveIntegerField(null=True, blank=True)
    item_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def has_participant(self, user):
        return user.pk in (self.user1_id, self.user2_id)

    def other_user(self, user):
        return self.user2 if user.pk == self.user1_id else self.user1

    def __str__(self):
        return f'{self.user1} - {self.user2}'


class Message(models.Model):
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Teks'
        LOCATION = 'location', 'Lokasi'

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='sent_messages',
    )
    message_type = models.CharField(
        max_length=10, choices=MessageType.choices, default=MessageType.TEXT,
    )
    content = models.TextField(blank=True)
    # Dipakai kalau message_type == location
    place_name = models.CharField(max_length=150, blank=True)
    address = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_edited = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender}: {self.content[:30]}'