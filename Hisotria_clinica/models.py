from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator

# Create your models here.

class Estudiante(models.Model):
    class Tipo(models.TextChoices):
        ESTUDIANTE = 'estudiante', 'Estudiante'
        PROFESOR = 'profesor', 'Profesor'
        OBRERO_TECNICO = 'obrero_tecnico', 'Personal Obrero/Técnico'
        ADMINISTRATIVO = 'administrativo', 'Personal Administrativo'
        EXTERNO = 'externo', 'Paciente Externo'

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    cedula = models.CharField(max_length=20, null=False, blank=True, unique=True)
    edad = models.IntegerField()
    edo_civil = models.CharField(max_length=50)
    sexo = models.CharField(max_length=10)
    direccion = models.CharField(max_length=200)
    contacto_emergencia = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20)
    fecha_nacimiento = models.DateField()
    fecha_registro = models.DateTimeField(auto_now_add=True)
    # NULL represents an unverified historical classification, never a sixth type.
    tipo_paciente = models.CharField(max_length=24, choices=Tipo.choices, null=True, blank=True, default=None)
    pnf = models.CharField('PNF', max_length=150, blank=True)
    cargo_laboral = models.CharField('Cargo', max_length=150, blank=True)
    lugar_nacimiento = models.CharField('Lugar de nacimiento', max_length=150, blank=True, default='')
    parentesco_emergencia = models.CharField('Parentesco del contacto de emergencia', max_length=100, blank=True, default='')
    telefono_emergencia = models.CharField('Teléfono del contacto de emergencia', max_length=20, blank=True, default='')
    # New records only; historical identifiers remain untouched and unmerged.
    cedula_clave = models.CharField(max_length=20, null=True, blank=True, unique=True, editable=False)

    @property
    def categoria_visible(self):
        return self.get_tipo_paciente_display() if self.tipo_paciente else 'Por verificar'

    @property
    def edad_actual(self):
        today = timezone.localdate()
        birth = self.fecha_nacimiento
        return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class AuditoriaPaciente(models.Model):
    paciente = models.ForeignKey(Estudiante, on_delete=models.PROTECT, related_name='cambios_personales')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=16)
    anteriores = models.JSONField(default=dict)
    nuevos = models.JSONField(default=dict)

    class Meta:
        ordering = ['-fecha', '-pk']


class HistoriaClinica(models.Model):
    estudiante = models.ForeignKey(Estudiante, on_delete=models.PROTECT)
    fecha_consulta = models.DateField()
    motivo_consulta = models.TextField()
    diagnostico = models.TextField()
    tratamiento = models.TextField()
    observaciones = models.TextField(blank=True, null=True)
    enfermedad_actual = models.TextField('Enfermedad actual', blank=True, default='')
    diagnostico_provisional = models.TextField('Diagnóstico provisional', blank=True, default='')
    atencion = models.OneToOneField('Atencion', null=True, blank=True, on_delete=models.PROTECT, related_name='historia')
    medico = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='consultas_medicas')
    version = models.PositiveIntegerField(default=0)

    # NULL preserves absence of information in historical consultations.
    # These codes are independent of clinical text and must never be renamed.
    rp = models.BooleanField('RP', null=True, blank=True, default=None)
    t_de_c = models.BooleanField('T de C', null=True, blank=True, default=None)
    tto = models.BooleanField('Tto', null=True, blank=True, default=None)
    lab = models.BooleanField('Lab', null=True, blank=True, default=None)
    ref = models.BooleanField('Ref', null=True, blank=True, default=None)
    imag = models.BooleanField('Imag', null=True, blank=True, default=None)
    rx = models.BooleanField('Rx', null=True, blank=True, default=None)
    cit = models.BooleanField('Cit', null=True, blank=True, default=None)

    @property
    def daily_option_groups(self):
        from .daily_options import option_groups
        return option_groups(self)

    def __str__(self):
        return f"Historia Clinica de {self.estudiante.nombre} {self.estudiante.apellido} - {self.fecha_consulta}"


class Atencion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        EN_ATENCION = 'en_atencion', 'En atención'
        ATENDIDO = 'atendido', 'Atendido'
        CANCELADO = 'cancelado', 'Cancelado / no atendido'

    paciente = models.ForeignKey(Estudiante, on_delete=models.PROTECT, related_name='atenciones')
    fecha_hora_llegada = models.DateTimeField()
    motivo_visita = models.TextField()
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='llegadas_registradas')
    actualizada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='atenciones_actualizadas')
    actualizada_en = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=0)
    turno = models.CharField(max_length=50, blank=True)
    enfermera_responsable = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name='atenciones_enfermeria')

    class Meta:
        ordering = ['fecha_hora_llegada', 'pk']
        constraints = [models.UniqueConstraint(fields=['paciente'], condition=models.Q(estado__in=['pendiente', 'en_atencion']), name='una_atencion_abierta_por_paciente')]


class CambioEstadoAtencion(models.Model):
    atencion = models.ForeignKey(Atencion, on_delete=models.PROTECT, related_name='cambios_estado')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    anterior = models.CharField(max_length=16, blank=True)
    nuevo = models.CharField(max_length=16, choices=Atencion.Estado.choices)

    class Meta:
        ordering = ['fecha', 'pk']


class AuditoriaClinica(models.Model):
    historia = models.ForeignKey(HistoriaClinica, on_delete=models.PROTECT, related_name='cambios_clinicos')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    motivo = models.TextField()
    anteriores = models.JSONField(default=dict)
    nuevos = models.JSONField(default=dict)

    class Meta:
        ordering = ['-fecha', '-pk']


class ConstanciaReposo(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'borrador', 'Borrador'
        EMITIDA = 'emitida', 'Emitida'

    historia = models.ForeignKey(HistoriaClinica, on_delete=models.PROTECT, related_name='constancias_reposo')
    anterior = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='siguiente_version')
    numero_version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.BORRADOR)
    motivo_reposo = models.TextField()
    dias = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    motivo_correccion = models.TextField(blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reposos_preparados')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    revision = models.PositiveIntegerField(default=0)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.PROTECT, related_name='reposos_aprobados')
    aprobado_en = models.DateTimeField(null=True, blank=True)
    datos_emitidos = models.JSONField(default=dict, editable=False)
    pdf = models.BinaryField(default=bytes, editable=False)
    pdf_sha256 = models.CharField(max_length=64, blank=True, editable=False)

    class Meta:
        ordering = ['-numero_version', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['historia', 'numero_version'], name='reposo_version_unica'),
            models.UniqueConstraint(fields=['historia'], condition=models.Q(estado='borrador'), name='un_borrador_reposo_por_consulta'),
            models.CheckConstraint(condition=models.Q(dias__gte=1, numero_version__gte=1), name='reposo_dias_version_positivos'),
            models.CheckConstraint(condition=models.Q(fecha_fin__gte=models.F('fecha_inicio')), name='reposo_periodo_coherente'),
            models.CheckConstraint(condition=(
                models.Q(estado='borrador', aprobado_por__isnull=True, aprobado_en__isnull=True, pdf_sha256='', pdf=b'', datos_emitidos={}) |
                (models.Q(estado='emitida', aprobado_por__isnull=False, aprobado_en__isnull=False) &
                 ~models.Q(pdf_sha256='') & ~models.Q(pdf=b'') & ~models.Q(datos_emitidos={}))
            ), name='reposo_emision_completa'),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, estado=self.Estado.EMITIDA).exists():
            raise ValidationError('Una constancia emitida es inmutable. Prepara una nueva versión.')
        if self.estado == self.Estado.EMITIDA:
            raise ValidationError('La emisión debe realizarse mediante el servicio de aprobación médica.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Las constancias se conservan. No se permite su eliminación ordinaria.')
