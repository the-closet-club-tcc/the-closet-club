from django.shortcuts import render

# Create your views here.
def swap_page(request):
    items = [
        {
            "name": "Blue Tie-Dye Asymmetrical Shirt",
            "description": "A pre-loved statement piece ready for its next wardrobe.",
            "image": "img/swap-shirt.png",
            "size": "M",
            "condition": "Good",
            "owner": "Demo User",
        },
        {
            "name": "Vintage Denim Jacket",
            "description": "Classic denim jacket in great condition.",
            "image": "img/swap-jacket.jpg",
            "size": "L",
            "condition": "Very Good",
            "owner": "Demo User 2",
        },
    ]
    
    return render(request, 'swap.html', {"items": items})