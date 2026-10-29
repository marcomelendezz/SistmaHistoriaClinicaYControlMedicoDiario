from django.urls import path
from . import views
from . import views_reposos

urlpatterns = [
    path('consulta/<int:history_id>/reposos/nuevo/', views_reposos.nuevo_reposo_view, name='nuevo_reposo'),
    path('reposos/<int:pk>/', views_reposos.detalle_reposo_view, name='detalle_reposo'),
    path('reposos/<int:pk>/editar/', views_reposos.editar_reposo_view, name='editar_reposo'),
    path('reposos/<int:pk>/aprobar/', views_reposos.aprobar_reposo_view, name='aprobar_reposo'),
    path('reposos/<int:pk>/vista-previa/', views_reposos.preview_reposo_view, name='preview_reposo'),
    path('reposos/<int:pk>/pdf/', views_reposos.reposo_pdf_view, name='reposo_pdf'),
    path('reposos/<int:pk>/imprimir/', views_reposos.imprimir_reposo_view, name='imprimir_reposo'),
    path('consulta/<int:pk>/pdf/', views.historia_pdf_view, name='historia_pdf'),
    path('consulta/<int:pk>/imprimir/', views.imprimir_historia_view, name='imprimir_historia'),
    path('reportes/registro-diario/pdf/', views.registro_diario_pdf_view, name='registro_diario_pdf'),
    path('reportes/registro-diario/imprimir/', views.imprimir_registro_diario_view, name='imprimir_registro_diario'),
    path('reportes/registro-diario/', views.registro_diario_view, name='registro_diario'),
    path('reportes/pendientes/', views.reporte_pendientes_view, name='reporte_pendientes'),
    path('atenciones/', views.lista_atenciones_view, name='lista_atenciones'),
    path('atenciones/<int:pk>/estado/', views.cambiar_estado_view, name='cambiar_estado'),
    path('atenciones/<int:pk>/consulta/', views.consulta_medica_view, name='consulta_medica'),
    path('consulta/<int:pk>/corregir/', views.corregir_historia_view, name='corregir_historia'),
    path('pacientes/', views.lista_pacientes_view, name='lista_pacientes'),
    path('pacientes/<int:pk>/', views.detalle_paciente_view, name='detalle_paciente'),
    path('pacientes/<int:pk>/editar/', views.editar_paciente_view, name='editar_paciente'),
    path('pacientes/registro/', views.registro_paciente_view, name='registro_paciente'),
    path('consulta/<int:pk>/', views.detalle_historia_view, name='detalle_historia'),
    path('registro_historia/', views.registro_historia_view, name='registro_historia'),
    path('nueva_consulta/', views.nueva_consulta_view, name='nueva_consulta'),
    path('lista_historia/', views.lista_historia_view, name='lista_historia')
]
