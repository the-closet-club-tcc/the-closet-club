from django.shortcuts import render

# Create your views here.
def swap_page(request):
    return render(request, 'swap.html')