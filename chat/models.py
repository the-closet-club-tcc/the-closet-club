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
    cleared_at_user1 = models.DateTimeField(null=True, blank=True)
    cleared_at_user2 = models.DateTimeField(null=True, blank=True)
    accepted = models.BooleanField(default=True)

    def cleared_at_for(self, user):
        return self.cleared_at_user1 if user.pk == self.user1_id else self.cleared_at_user2

    def visible_messages(self, user):
        """Pesan yang masih terlihat oleh user (setelah ia menghapus percakapan)."""
        qs = self.messages.all()
        cleared = self.cleared_at_for(user)
        if cleared:
            qs = qs.filter(created_at__gt=cleared)
        return qs    

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
        TEXT = 'text', 'Text'
        LOCATION = 'location', 'Location'
        IMAGE = 'image', 'Photo'
        FILE = 'file', 'Document'
        SWAP = 'swap', 'Swap request'       

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
    attachment_name = models.CharField(max_length=255, blank=True)
    attachment_type = models.CharField(max_length=100, blank=True)
    attachment_size = models.PositiveIntegerField(default=0)

    reply_to = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies',
    )
    has_reply = models.BooleanField(default=False)
    swap_request = models.ForeignKey(
        'swap.SwapRequest', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='chat_messages',
    )    

    def preview_text(self):
        if self.message_type == self.MessageType.LOCATION:
            return f'Location: {self.place_name}'
        if self.message_type == self.MessageType.IMAGE:
            return 'Photo'
        if self.message_type == self.MessageType.FILE:
            return f'Document: {self.attachment_name}'
        if self.message_type == self.MessageType.SWAP:
            return 'Swap request'        
        return self.content

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['swap_request'],
                condition=models.Q(message_type='swap'),
                name='unique_swap_card_per_request',
            ),
        ]

    def __str__(self):
        return f'{self.sender}: {self.content[:30]}'

class Attachment(models.Model):
    message = models.OneToOneField(
        Message, on_delete=models.CASCADE, related_name='attachment',
    )
    data = models.BinaryField()

class Block(models.Model):
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocks_made',
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocks_received',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['blocker', 'blocked'], name='unique_block'),
        ]

    def __str__(self):
        return f'{self.blocker} blocked {self.blocked}'


class Report(models.Model):
    class Reason(models.TextChoices):
        SPAM = 'spam', 'Spam or promotion'
        SCAM = 'penipuan', 'Scam'
        HARASSMENT = 'pelecehan', 'Harassment or offensive language'
        INAPPROPRIATE = 'tidak_pantas', 'Inappropriate content'
        OTHER = 'lainnya', 'Other'

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reports_made',
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reports_received',
    )
    message = models.ForeignKey(
        Message, null=True, blank=True, on_delete=models.SET_NULL, related_name='reports',
    )
    message_excerpt = models.CharField(max_length=300, blank=True)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    detail = models.TextField(blank=True)
    is_reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reporter} reported {self.reported_user} ({self.reason})'