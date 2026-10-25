from django.urls import path

from . import views

app_name = 'closet'

urlpatterns = [
    path('', views.my_closet, name='my_closet'),
    path('add/', views.item_create, name='item_add'),
    path('item/<int:pk>/', views.item_detail, name='item_detail'),
    path('item/<int:pk>/edit/', views.item_edit, name='item_edit'),
    path('item/<int:pk>/delete/', views.item_delete, name='item_delete'),
    path('item/<int:pk>/status/', views.item_status, name='item_status'),
    path('u/<str:username>/', views.user_closet, name='user_closet'),
]
