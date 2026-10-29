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
    path('requests/<int:pk>/counter/', views.counter_offer, name='counter_offer'),
    path('requests/<int:pk>/counter/', views.counter_offer, name='choose_counter'),
    path('requests/<int:pk>/decline/', views.update_request_status, {'action': 'decline'}, name='decline'),
    path('requests/<int:pk>/agree/', views.update_request_status, {'action': 'accept'}, name='agree'),
    path('requests/<int:pk>/complete/', views.update_request_status, {'action': 'complete'}, name='complete'),
    path('requests/<int:pk>/cancel/', views.update_request_status, {'action': 'cancel'}, name='cancel'),
    path('requests/<int:pk>/chat/', views.open_request_chat, name='open_chat'),
    path('requests/<int:pk>/review/', views.review_swap, name='review'),
    path('requests/<int:pk>/<str:action>/', views.update_request_status, name='update_request_status'),
]
