from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from closet.models import Clothing
from .forms import OutfitPostForm
from .models import OutfitPost

PAGE_SIZE = 9

SORT_OPTIONS = [
    ('new', 'Newest', '-created_at'),
    ('popular', 'Most liked', '-like_count'),
    ('oldest', 'Oldest', 'created_at'),
]

# Only "offered" statuses are meaningful as a feed filter (not personal / swapped)
OFFER_CHOICES = [(s.value, s.label) for s in Clothing.OFFER_STATUSES]


def feed_list(request):
    """Public feed (guests can browse). Supports search, filters, sorting, pagination."""
    posts = (
        OutfitPost.objects
        .select_related('author')
        .prefetch_related('clothes')
        .annotate(like_count=Count('likes', distinct=True))
    )

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

    # One filter() call, so a single tagged item must match ALL chosen filters
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

    page_obj = Paginator(posts, PAGE_SIZE).get_page(request.GET.get('page'))

    # Query string without "page", so pagination links keep the filters
    params = request.GET.copy()
    params.pop('page', None)

    context = {
        'page_obj': page_obj,
        'q': q,
        'selected_sizes': sizes,
        'selected_conditions': conditions,
        'selected_offers': offers,
        'sort': sort,
        'sort_options': [(key, label) for key, label, _ in SORT_OPTIONS],
        'size_choices': Clothing.Size.choices,
        'condition_choices': Clothing.Condition.choices,
        'offer_choices': OFFER_CHOICES,
        'querystring': params.urlencode(),
        'has_filters': bool(q or sizes or conditions or offers),
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
        'is_author': request.user.is_authenticated and request.user == post.author,
    }
    return render(request, 'feed/post_detail.html', context)


@login_required(login_url='login')
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
        'has_clothes': Clothing.objects.filter(owner=request.user).exists(),
    })


@login_required(login_url='login')
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


@login_required(login_url='login')
@require_POST
def post_delete(request, pk):
    post = get_object_or_404(OutfitPost, pk=pk, author=request.user)  # only the author
    post.delete()
    return redirect('feed:index')