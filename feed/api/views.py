from django.core.paginator import EmptyPage, Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from closet.models import Clothing
from feed.models import OutfitPost
from feed.views import OFFER_CHOICES, PAGE_SIZE, SORT_OPTIONS
from .authentication import CsrfExemptSessionAuthentication
from .serializers import ClothingMiniSerializer, PostCreateSerializer, PostSerializer


def _posts_queryset():
    return (
        OutfitPost.objects
        .select_related('author')
        .prefetch_related('clothes')
        .annotate(like_count=Count('likes', distinct=True))
    )


class FeedAPIView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAuthenticatedOrReadOnly]


class PostListCreateAPI(FeedAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        posts = _posts_queryset()

        q = request.GET.get('q', '').strip()
        sizes = [s for s in request.GET.getlist('size') if s in Clothing.Size.values]
        conditions = [c for c in request.GET.getlist('condition') if c in Clothing.Condition.values]
        offers = [o for o in request.GET.getlist('offer') if o in dict(OFFER_CHOICES)]
        sort = request.GET.get('sort', 'new')
        if sort not in {key for key, _, _ in SORT_OPTIONS}:
            sort = 'new'

        if q:
            posts = posts.filter(
                Q(caption__icontains=q)
                | Q(author__username__icontains=q)
                | Q(clothes__name__icontains=q)
            )

        # Satu filter() supaya satu item yang di-tag harus cocok dengan SEMUA filter
        item_filter = {}
        if sizes:
            item_filter['clothes__size__in'] = sizes
        if conditions:
            item_filter['clothes__condition__in'] = conditions
        if offers:
            item_filter['clothes__status__in'] = offers
        if item_filter:
            posts = posts.filter(**item_filter)

        order_by = next(o for key, _, o in SORT_OPTIONS if key == sort)
        posts = posts.distinct().order_by(order_by, '-created_at')

        paginator = Paginator(posts, PAGE_SIZE)
        try:
            page = paginator.page(request.GET.get('page') or 1)
        except (EmptyPage, ValueError):
            return Response({
                'count': paginator.count, 'page': 0,
                'num_pages': paginator.num_pages, 'has_next': False, 'results': [],
            })

        data = PostSerializer(page.object_list, many=True, context={'request': request}).data
        return Response({
            'count': paginator.count,
            'page': page.number,
            'num_pages': paginator.num_pages,
            'has_next': page.has_next(),
            'results': data,
        })

    def post(self, request):
        serializer = PostCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        post = OutfitPost.objects.create(
            author=request.user,
            image=vd['image'],
            caption=vd.get('caption', ''),
        )
        post.clothes.set(vd.get('clothes', []))
        return Response(PostSerializer(post, context={'request': request}).data, status=201)


class PostDetailAPI(FeedAPIView):
    def get(self, request, pk):
        post = get_object_or_404(_posts_queryset(), pk=pk)
        return Response(PostSerializer(post, context={'request': request}).data)

    def delete(self, request, pk):
        post = get_object_or_404(OutfitPost, pk=pk, author=request.user)  # hanya author
        post.delete()
        return Response(status=204)


class PostLikeAPI(FeedAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        post = get_object_or_404(OutfitPost, pk=pk)
        if post.likes.filter(pk=request.user.pk).exists():
            post.likes.remove(request.user)
            liked = False
        else:
            post.likes.add(request.user)
            liked = True
        return Response({'liked': liked, 'like_count': post.likes.count()})


class MyClothesAPI(FeedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = Clothing.objects.filter(owner=request.user)
        return Response(ClothingMiniSerializer(items, many=True, context={'request': request}).data)