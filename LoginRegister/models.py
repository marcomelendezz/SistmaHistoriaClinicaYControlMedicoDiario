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
        if not extra_fields['is_staff'] or not extra_fields['is_superuser']:
            raise ValueError('Un superusuario requiere is_staff e is_superuser.')
        # Only bootstrap_admin or an explicit administrator decision approves access.
        return self.create_user(email, password, **extra_fields)

class Usuario(AbstractUser):
    CARGOS = (
        ('Medico', 'medico'),
        ('Enfermero/a','enfermero'),
    )

    username = None
    # Campos requeridos por tu especificación
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    apellido = models.CharField(max_length=100, verbose_name="Apellido")
    email = models.EmailField(unique=True, verbose_name="Correo Electrónico")
    cargo = models.CharField(max_length=20, choices=CARGOS, default='enfermero', verbose_name="Cargo")

    # Indicar a Django que se loguee con el Email
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre', 'apellido']

    objects = CustomUserManager()

    class Role(models.TextChoices):
        DOCTOR = 'medico', 'Médico'
        NURSE = 'enfermera', 'Enfermera'
        ADMIN = 'administrador', 'Administrador'

    class Status(models.TextChoices):
        LEGACY = 'legacy', 'Cuenta antigua por revisar'
        PENDING = 'pendiente', 'Pendiente de aprobación'
        APPROVED = 'aprobado', 'Aprobado'
        REJECTED = 'rechazado', 'Rechazado'

    # cargo is preserved as historical information, never as authorization.
    requested_role = models.CharField(max_length=20, blank=True, choices=Role.choices)
    authorized_role = models.CharField(max_length=20, blank=True, choices=Role.choices)
    approval_status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reviewed_accounts')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.TextField(blank=True)

    def __str__(self):
        return f'{self.nombre} {self.apellido}'


class AccountAudit(models.Model):
    actor = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='account_actions')
    target = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='account_changes')
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=32)
    reason = models.TextField(blank=True)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)

    class Meta:
        ordering = ['-created_at', '-pk']
