# loginregister/urls.py
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    # Agrega tus rutas aquí, por ejemplo:
    path('', auth_views.LoginView.as_view(template_name='LoginRegister/login.html'), name='login'),
    path('registro/',views.register_view, name='register'),
]