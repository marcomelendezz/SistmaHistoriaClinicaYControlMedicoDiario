
from django.urls import path, reverse_lazy
from . import views
from django.contrib.auth import views as auth_views
from .forms import CustomLoginForm

urlpatterns = [
    path('', auth_views.LoginView.as_view(
        template_name='LoginRegister/login.html',
        authentication_form=CustomLoginForm,
    ), name='login'),
    path('registro/', views.register_view, name='register'),
    path('cuentas/', views.account_list, name='account_list'),
    path('cuentas/auditoria/', views.account_audit, name='account_audit'),
    path('cuentas/<int:pk>/', views.account_review, name='account_review'),
    path('bloqueo/', views.blocked_view, name='blocked'),
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='LoginRegister/accounts/passwor_reset.html',
            email_template_name='LoginRegister/accounts/password_reset_email.html',
            subject_template_name='LoginRegister/accounts/password_reset_subject.txt',
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='LoginRegister/accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'password-reset/<uidb64>/<token>/',
        views.CustomPasswordResetConfirmView.as_view(
            template_name='LoginRegister/accounts/password_reset_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='LoginRegister/accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
]
