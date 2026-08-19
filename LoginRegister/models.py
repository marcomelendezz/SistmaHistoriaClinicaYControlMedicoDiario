from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

# Create your models here.

# manager personalizado para el modelo de usuario

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El correo electrónico es obligatorio')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class Usuario(AbstractUser):
    CARGOS = (
        ('medico', 'Médico'),
        ('enfermero', 'Enfermero/a'),
    )

    username = None
    # Campos requeridos por tu especificación
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    apellido = models.CharField(max_length=100, verbose_name="Apellido")
    email = models.EmailField(unique=True, verbose_name="Correo Electrónico")
    cargo = models.CharField(max_length=20, choices=CARGOS, default='enfermero', verbose_name="Cargo")

    # Indicar a Django que se loguee con el Email
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name'] # Campos al crear superuser por consola

    objects = CustomUserManager()

def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.get_cargo_display()})"