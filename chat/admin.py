from django.contrib import admin

from .models import Block, Conversation, Message, Report

admin.site.register(Conversation)
admin.site.register(Message)
admin.site.register(Block)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'reporter', 'reported_user', 'reason', 'is_reviewed')
    list_filter = ('reason', 'is_reviewed')
    list_editable = ('is_reviewed',)
    search_fields = ('reporter__username', 'reported_user__username', 'detail', 'message_excerpt')
    readonly_fields = ('created_at',)