from django.contrib import admin

from .models import Clothing


@admin.register(Clothing)
class ClothingAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'size', 'condition', 'status', 'created_at')
    list_filter = ('status', 'size', 'condition')
    search_fields = ('name', 'description', 'owner__username')
