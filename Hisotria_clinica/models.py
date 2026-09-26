from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

# Create your models here.

class Estudiante(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    edad = models.IntegerField()
    edo_civil = models.CharField(max_length=50)
    sexo = models.CharField(max_length=10)
    direccion = models.CharField(max_length=200)
    contacto_emergencia = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20)
    fecha_nacimiento = models.DateField()
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class HistoriaClinica(models.Model):
    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE)
    fecha_consulta = models.DateField()
    motivo_consulta = models.TextField()
    diagnostico = models.TextField()
    tratamiento = models.TextField()
    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Historia Clinica de {self.estudiante.nombre} {self.estudiante.apellido} - {self.fecha_consulta}"