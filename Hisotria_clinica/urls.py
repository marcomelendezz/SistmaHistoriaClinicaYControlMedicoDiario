from django.urls import path
from . import views

urlpatterns = [
    path('', views.registro_historia_view, name='registro_historia'),
]