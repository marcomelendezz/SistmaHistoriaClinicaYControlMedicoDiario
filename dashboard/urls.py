from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [

    path('dashboard/', views.dashboard_view, name='dashboard'),
]