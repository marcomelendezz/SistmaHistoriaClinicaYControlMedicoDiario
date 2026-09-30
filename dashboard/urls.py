from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('mi_perfil/', views.mi_perfil_view, name='mi_perfil'),
]