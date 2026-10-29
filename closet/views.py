from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ClothingForm
from .models import Clothing

PAGE_SIZE = 12


def _apply_filters(qs, params, allow_status=False):
    """Pencarian + filter ukuran/kondisi (+ status untuk closet milik sendiri)."""
    q = params.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    size = params.get('size', '')
    if size in Clothing.Size.values:
        qs = qs.filter(size=size)
    condition = params.get('condition', '')
    if condition in Clothing.Condition.values:
        qs = qs.filter(condition=condition)
    if allow_status:
        status = params.get('status', '')
        if status in Clothing.Status.values:
            qs = qs.filter(status=status)
    return qs


def _paginate(request, qs):
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return page, params.urlencode()


def _filter_context(request):
    return {
        'q': request.GET.get('q', '').strip(),
        'sel_size': request.GET.get('size', ''),
        'sel_condition': request.GET.get('condition', ''),
        'size_choices': Clothing.Size.choices,
        'condition_choices': Clothing.Condition.choices,
    }


@login_required(login_url='login')
def my_closet(request):
    base = request.user.clothes.all()

    # Jumlah item per status (tidak terpengaruh filter lain) untuk tab
    counts = {r['status']: r['n'] for r in base.values('status').annotate(n=Count('id'))}
    current = request.GET.get('status', '')
    if current not in Clothing.Status.values:
        current = ''
    tabs = [{'value': '', 'label': 'All', 'count': sum(counts.values()), 'active': current == ''}]
    for value, label in Clothing.Status.choices:
        tabs.append({
            'value': value, 'label': label,
            'count': counts.get(value, 0), 'active': current == value,
        })

    qs = _apply_filters(base, request.GET, allow_status=True)
    page, querystring = _paginate(request, qs)

    context = {
        'page': page,
        'querystring': querystring,
        'tabs': tabs,
        'current_status': current,
        'status_choices': Clothing.Status.choices,
        'offered_count': sum(counts.get(s, 0) for s in Clothing.OFFER_STATUSES),
        'total_count': sum(counts.values()),
        'is_filtered': bool(querystring),
    }
    context.update(_filter_context(request))
    return render(request, 'closet/my_closet.html', context)


def user_closet(request, username):
    """Katalog publik: hanya pakaian yang sedang ditawarkan. Bisa diakses guest."""
    owner = get_object_or_404(get_user_model(), username=username)
    if request.user.is_authenticated and request.user == owner:
        return redirect('closet:index')

    qs = _apply_filters(owner.clothes.offered(), request.GET)
    page, querystring = _paginate(request, qs)

    context = {
        'owner': owner,
        'rating': owner.get_rata_rata_rating(),
        'page': page,
        'querystring': querystring,
        'is_filtered': bool(querystring),
    }
    context.update(_filter_context(request))
    return render(request, 'closet/user_closet.html', context)


def item_detail(request, pk):
    item = get_object_or_404(Clothing.objects.select_related('owner'), pk=pk)
    is_owner = request.user.is_authenticated and item.owner_id == request.user.id
    # Koleksi pribadi hanya boleh dilihat pemiliknya
    if item.status == Clothing.Status.PERSONAL and not is_owner:
        raise Http404
    return render(request, 'closet/item_detail.html', {
        'item': item,
        'is_owner': is_owner,
        'owner': item.owner,
        'rating': item.owner.get_rata_rata_rating(),
    })


@login_required(login_url='login')
def item_create(request):
    form = ClothingForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.owner = request.user
        item.save()
        messages.success(request, f'"{item.name}" was added to your closet.')
        return redirect('closet:index')
    return render(request, 'closet/item_form.html', {'form': form, 'item': None})


@login_required(login_url='login')
def item_edit(request, pk):
    # Item milik user lain -> 404
    item = get_object_or_404(Clothing, pk=pk, owner=request.user)
    form = ClothingForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'"{item.name}" was updated.')
        return redirect('closet:index')
    return render(request, 'closet/item_form.html', {'form': form, 'item': item})


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def item_delete(request, pk):
    item = get_object_or_404(Clothing, pk=pk, owner=request.user)
    if request.method == 'POST':
        name = item.name
        item.delete()
        messages.success(request, f'"{name}" was removed from your closet.')
        return redirect('closet:index')
    return render(request, 'closet/item_confirm_delete.html', {'item': item})


@login_required(login_url='login')
@require_POST
def item_status(request, pk):
    item = get_object_or_404(Clothing, pk=pk, owner=request.user)
    status = request.POST.get('status', '')
    if status in Clothing.Status.values:
        item.status = status
        item.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'"{item.name}" is now: {item.get_status_display()}.')
    else:
        messages.error(request, 'Invalid availability status.')

    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('closet:index')
