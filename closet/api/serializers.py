from rest_framework import serializers

from closet.models import Clothing


class ClothingSerializer(serializers.ModelSerializer):
    owner = serializers.CharField(source='owner.username', read_only=True)
    photo = serializers.SerializerMethodField()
    size_display = serializers.CharField(source='get_size_display', read_only=True)
    condition_display = serializers.CharField(source='get_condition_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Clothing
        fields = [
            'id', 'name', 'photo', 'size', 'size_display',
            'condition', 'condition_display', 'description',
            'status', 'status_display', 'owner', 'created_at',
        ]

    def get_photo(self, obj):
        if not obj.photo:
            return None
        url = obj.photo.url
        request = self.context.get('request')
        if request and url.startswith('/'):
            return request.build_absolute_uri(url)  # lokal: /media/... jadi absolut
        return url  # Cloudinary sudah absolut
