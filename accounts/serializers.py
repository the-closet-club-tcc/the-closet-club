from rest_framework import serializers
from .models import Review, User, Verification


class UserSerializer(serializers.ModelSerializer):
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "foto_profil",
            "is_verified",
            "bio",
            "lokasi",
            "average_rating",
        ]
        read_only_fields = ["id", "username", "is_verified", "average_rating"]

    def get_fields(self):
        fields = super().get_fields()
        instance = getattr(self, "instance", None)
        if instance is not None and instance.is_verified:
            for name in ("first_name", "last_name", "email"):
                fields[name].read_only = True
        return fields

    def get_average_rating(self, obj):
        return obj.get_rata_rata_rating()


class VerificationSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Verification
        fields = ["id", "username", "status", "tanggal_pengajuan"]
        read_only_fields = ["id", "username", "status", "tanggal_pengajuan"]


class ReviewSerializer(serializers.ModelSerializer):
    pemberi_username = serializers.CharField(source="pemberi_review.username", read_only=True)
    penerima_username = serializers.CharField(source="penerima_review.username", read_only=True)

    class Meta:
        model = Review
        fields = [
            "id",
            "pemberi_username",
            "penerima_username",
            "swap_request",
            "rating",
            "komentar",
            "tanggal",
        ]
    
        read_only_fields = [
            "id",
            "pemberi_username",
            "penerima_username",
            "swap_request",
            "rating",
            "komentar",
            "tanggal",
        ]
