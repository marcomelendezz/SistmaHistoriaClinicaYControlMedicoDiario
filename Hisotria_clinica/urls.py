from django.urls import path
from . import views

urlpatterns = [
    path('registro_historia/', views.registro_historia_view, name='registro_historia'),
    path('lista_historia/', views.lista_historia_view, name='lista_historia')
]