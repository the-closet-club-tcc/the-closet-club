from django.urls import path
from . import views

urlpatterns = [
    path('posts/', views.PostListCreateAPI.as_view(), name='api_feed_posts'),
    path('posts/<int:pk>/', views.PostDetailAPI.as_view(), name='api_feed_post_detail'),
    path('posts/<int:pk>/like/', views.PostLikeAPI.as_view(), name='api_feed_like'),
    path('my-clothes/', views.MyClothesAPI.as_view(), name='api_feed_my_clothes'),
]