from django.contrib import admin
from .models import OutfitPost


@admin.register(OutfitPost)
class OutfitPostAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'created_at')
    search_fields = ('caption', 'author__username')
    filter_horizontal = ('clothes',)