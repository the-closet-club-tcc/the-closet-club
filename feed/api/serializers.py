from rest_framework import serializers

from closet.models import Clothing
from feed.models import OutfitPost

MAX_IMAGE_MB = 5


def _abs_url(request, field):
    """Pakai URL absolut supaya bisa dimuat Image.network di Flutter."""
    if not field:
        return None
    url = field.url
    if request and url.startswith('/'):
        return request.build_absolute_uri(url)  # lokal: /media/... jadi absolut
    return url  # Cloudinary sudah absolut


class AuthorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    is_verified = serializers.BooleanField()
    avatar = serializers.SerializerMethodField()

    def get_avatar(self, obj):
        return _abs_url(self.context.get('request'), obj.foto_profil)


class ClothingMiniSerializer(serializers.ModelSerializer):
    photo = serializers.SerializerMethodField()
    size_label = serializers.CharField(source='get_size_display', read_only=True)
    condition_label = serializers.CharField(source='get_condition_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Clothing
        fields = [
            'id', 'name', 'photo',
            'size', 'size_label',
            'condition', 'condition_label',
            'status', 'status_label',
        ]

    def get_photo(self, obj):
        return _abs_url(self.context.get('request'), obj.photo)


class PostSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    image = serializers.SerializerMethodField()
    clothes = ClothingMiniSerializer(many=True, read_only=True)
    like_count = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    is_author = serializers.SerializerMethodField()

    class Meta:
        model = OutfitPost
        fields = [
            'id', 'author', 'image', 'caption', 'clothes',
            'like_count', 'liked', 'is_author', 'created_at',
        ]

    def get_image(self, obj):
        return _abs_url(self.context.get('request'), obj.image)

    def get_like_count(self, obj):
        annotated = getattr(obj, 'like_count', None)  # dari annotate() di list view
        return annotated if annotated is not None else obj.likes.count()

    def _user(self):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return user if user and user.is_authenticated else None

    def get_liked(self, obj):
        user = self._user()
        return bool(user and obj.likes.filter(pk=user.pk).exists())

    def get_is_author(self, obj):
        user = self._user()
        return bool(user and obj.author_id == user.pk)


class PostCreateSerializer(serializers.Serializer):
    image = serializers.ImageField()
    caption = serializers.CharField(required=False, allow_blank=True, max_length=500)
    clothes = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Clothing.objects.all(),
    )

    def validate_image(self, image):
        if image.size > MAX_IMAGE_MB * 1024 * 1024:
            raise serializers.ValidationError(f'Image must be under {MAX_IMAGE_MB} MB.')
        return image

    def validate_clothes(self, clothes):
        user = self.context['request'].user
        if any(c.owner_id != user.pk for c in clothes):
            raise serializers.ValidationError('You can only tag items from your own closet.')
        return clothes