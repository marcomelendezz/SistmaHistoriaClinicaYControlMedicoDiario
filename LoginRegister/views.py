from django.shortcuts import render

# Create your views here.
def register_view(request):
    if request.method == 'POST':
        # Aquí puedes manejar el registro del usuario
        # Por ejemplo, puedes crear un formulario de registro y validarlo
        # Si el formulario es válido, puedes crear un nuevo usuario
        # y redirigirlo a la página de inicio de sesión o a otra página
        pass
    else:
        # Si es una solicitud GET, simplemente renderiza la plantilla de registro
        return render(request, 'LoginRegister/register.html')