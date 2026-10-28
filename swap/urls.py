from django.urls import path
from . import views

app_name = 'swap'

urlpatterns = [
    path('', views.swap_page, name='index'),
    path('interested/', views.interested_items, name='interested'),
    path('items/<int:pk>/interest/', views.save_interest, name='save_interest'),
    path('interested/<int:pk>/remove/', views.remove_interest, name='remove_interest'),
    path('interested/<int:pk>/propose/', views.propose_swap, name='propose'),
    path('requests/incoming/', views.swap_requests, name='requests_incoming'),
    path('requests/outgoing/', views.swap_requests, {'direction': 'outgoing'}, name='requests_outgoing'),
    path('requests/<int:pk>/decline/', views.decline_swap, name='decline'),
    path('requests/<int:pk>/counter/', views.choose_counter, name='choose_counter'),
    path('requests/<int:pk>/agree/', views.agree_swap, name='agree'),
    path('requests/<int:pk>/complete/', views.complete_swap, name='complete'),
    path('requests/<int:pk>/cancel/', views.cancel_swap, name='cancel'),    
]
