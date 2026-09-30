from django.shortcuts import render

# Create your views here.

def dashboard_view(request):
    return render(request, 'dashboard/dashboard.html')

def mi_perfil_view(request):
    return render(request, 'dashboard/mi_perfil.html')