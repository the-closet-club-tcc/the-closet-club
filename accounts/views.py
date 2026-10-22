from django.shortcuts import render
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import CustomUserCreationForm

def register(request):
    # kalau user menekan submit/daftar
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save() # simpan ke database
            messages.success(request, 'Akun berhasil dibuat! Silakan login.')
            return redirect('login') # arahkan ke halaman login
    else:
        # kalau userbelum submit apa apa
        form = CustomUserCreationForm()
    
    return render(request, 'accounts/register.html', {'form': form})
