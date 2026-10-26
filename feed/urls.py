from django.urls import path
from . import views

app_name = 'feed'

urlpatterns = [
    path('', views.feed_list, name='index'),
    path('new/', views.post_create, name='create'),
    path('<int:pk>/', views.post_detail, name='detail'),
    path('<int:pk>/like/', views.toggle_like, name='like'),
    path('<int:pk>/delete/', views.post_delete, name='delete'),
]