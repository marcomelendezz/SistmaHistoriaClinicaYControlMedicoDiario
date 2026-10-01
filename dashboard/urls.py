from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('mi_perfil/', views.mi_perfil_view, name='mi_perfil'),
    path('mi_perfil/editar/', views.editar_perfil_view, name='editar_perfil'),
]