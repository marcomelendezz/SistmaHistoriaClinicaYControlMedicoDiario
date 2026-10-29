from axes.utils import reset
from django.contrib import messages
from django.contrib.auth.views import PasswordResetConfirmView
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from .access import capability_required
from .forms import AccountReviewForm, RegistroForm
from .services import account_audit_for, accounts_for, review_account


def register_view(request):
    form = RegistroForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Solicitud registrada. Debes esperar la aprobación administrativa antes de iniciar sesión.')
        return redirect('login')
    return render(request, 'LoginRegister/register.html', {'form': form})


def blocked_view(request):
    return render(request, 'LoginRegister/accounts/bloqueo.html')


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    def form_valid(self, form):
        response = super().form_valid(form)
        reset(username=form.user.email)
        return response


@capability_required('manage_accounts')
def account_list(request):
    return render(request, 'LoginRegister/accounts/list.html', {'accounts': accounts_for(request.user)})


@capability_required('manage_accounts')
def account_review(request, pk):
    account = get_object_or_404(accounts_for(request.user), pk=pk)
    form = AccountReviewForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            review_account(actor=request.user, target_id=account.pk, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'La autorización de la cuenta fue actualizada.')
            return redirect('account_list')
    return render(request, 'LoginRegister/accounts/review.html', {'account': account, 'form': form})


@capability_required('manage_accounts')
def account_audit(request):
    return render(request, 'LoginRegister/accounts/audit.html', {'events': account_audit_for(request.user)[:200]})
