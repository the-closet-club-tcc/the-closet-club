from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('chat/', include('chat.urls')),
    path('login/', lambda r: HttpResponse('login'), name='login'),
    path('register/', lambda r: HttpResponse('register'), name='register'),
    path('', lambda r: HttpResponse('home'), name='home'),
]