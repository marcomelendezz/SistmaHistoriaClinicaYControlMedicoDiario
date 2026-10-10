
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .forms import CustomLoginForm
from LoginRegister.views import CustomPasswordResetConfirmView

urlpatterns = [
    # Agrega tus rutas aquí, por ejemplo:
    path('', auth_views.LoginView.as_view(
        template_name='LoginRegister/login.html',
        authentication_form=CustomLoginForm,
    ), name='login'),
    path('registro/',views.register_view, name='register'),
    path('bloqueo/', views.blocked_view, name='blocked'),
]