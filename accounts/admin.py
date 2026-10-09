from django.contrib import admin

# Register your models here.
from .models import User, Verification, Review

admin.site.register(User)
admin.site.register(Verification)
admin.site.register(Review)