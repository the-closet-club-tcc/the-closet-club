from django.contrib import admin
from django.db import transaction
from .models import User, Verification, Review

admin.site.register(User)
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

    @transaction.atomic
    def save_model(self, request, obj, form, change):

        # simpan perubahan status Verification
        super().save_model(request, obj, form, change)
        # update status verified pada User
        obj.user.is_verified = (obj.status == "approved")
        # simpan perubahan ke database
        obj.user.save(update_fields=["is_verified"])
