from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from closet.models import Clothes
from .forms import OutfitPostForm
from .models import OutfitPost

PAGE_SIZE = 9

SORT_OPTIONS = [
    ('new', 'Newest', '-created_at'),
    ('popular', 'Most liked', '-like_count'),
    ('oldest', 'Oldest', 'created_at'),
]


def feed_list(request):
    """Public feed (guests can browse). Supports search, filters, sorting, pagination."""
    posts = (
        OutfitPost.objects
        .select_related('author')
        .prefetch_related('clothes')
        .annotate(like_count=Count('likes', distinct=True))
    )

    q = request.GET.get('q', '').strip()
    sizes = [s for s in request.GET.getlist('size') if s in dict(Clothes.SIZE_CHOICES)]
    conditions = [c for c in request.GET.getlist('condition') if c in dict(Clothes.CONDITION_CHOICES)]
    sort = request.GET.get('sort', 'new')
    if sort not in {key for key, _, _ in SORT_OPTIONS}:
        sort = 'new'

    if q:
        posts = posts.filter(
            Q(caption__icontains=q)
            | Q(author__username__icontains=q)
            | Q(clothes__name__icontains=q)
        )

    # One filter() call, so a single item must match BOTH size and condition
    item_filter = {}
    if sizes:
        item_filter['clothes__size__in'] = sizes
    if conditions:
        item_filter['clothes__condition__in'] = conditions
    if item_filter:
        posts = posts.filter(**item_filter)

    order_by = next(o for key, _, o in SORT_OPTIONS if key == sort)
    posts = posts.distinct().order_by(order_by, '-created_at')

    page_obj = Paginator(posts, PAGE_SIZE).get_page(request.GET.get('page'))

    # Query string without "page", so pagination links keep the filters
    params = request.GET.copy()
    params.pop('page', None)

    context = {
        'page_obj': page_obj,
        'q': q,
        'selected_sizes': sizes,
        'selected_conditions': conditions,
        'sort': sort,
        'sort_options': [(key, label) for key, label, _ in SORT_OPTIONS],
        'size_choices': Clothes.SIZE_CHOICES,
        'condition_choices': Clothes.CONDITION_CHOICES,
        'querystring': params.urlencode(),
        'has_filters': bool(q or sizes or conditions),
    }
    return render(request, 'feed/feed_list.html', context)


def post_detail(request, pk):
    post = get_object_or_404(
        OutfitPost.objects.select_related('author').prefetch_related('clothes'), pk=pk,
    )
    context = {
        'post': post,
        'like_count': post.likes.count(),
        'liked': request.user.is_authenticated and post.likes.filter(pk=request.user.pk).exists(),
    }
    return render(request, 'feed/post_detail.html', context)


@login_required
def post_create(request):
    form = OutfitPostForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        form.save_m2m()
        return redirect(post)
    return render(request, 'feed/post_form.html', {
        'form': form,
        'has_clothes': Clothes.objects.filter(owner=request.user).exists(),
    })


@login_required
@require_POST
def toggle_like(request, pk):
    post = get_object_or_404(OutfitPost, pk=pk)
    if post.likes.filter(pk=request.user.pk).exists():
        post.likes.remove(request.user)
    else:
        post.likes.add(request.user)

    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect(post)


@login_required
@require_POST
def post_delete(request, pk):
    post = get_object_or_404(OutfitPost, pk=pk, author=request.user)  # only the author
    post.delete()
    return redirect('feed:index')