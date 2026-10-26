from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Verification, Review

@admin.register(User)
class AccountUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Profile", {"fields": ("foto_profil", "bio", "lokasi", "is_verified")}),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj) + ("is_verified",)
        if obj and obj.is_verified:
            fields += ("first_name", "last_name", "email")
        return fields

admin.site.register(Review)

@admin.register(Verification)
class VerificationAdmin(admin.ModelAdmin):

    # kolom yang ditampilkan di daftar pengajuan
    list_display = (
        "user",
        "status",
        "tanggal_pengajuan"
    )
    # filter berdasarkan status verifikasi
    list_filter = ("status",)
    # cari pengajuan berdasarkan username
    search_fields = ("user__username",)

    # mengunci kolom user dan tanggal pengajuan agar admin tidak bisa mengubahnya
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ("user", "tanggal_pengajuan")
        return ("tanggal_pengajuan",)
