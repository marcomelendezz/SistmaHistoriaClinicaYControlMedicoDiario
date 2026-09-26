from django.shortcuts import render

# Create your views here.

def registro_historia_view(request):
    return render(request, 'historia/historia.html')