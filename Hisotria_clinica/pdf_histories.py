"""FOR-SSS-04: only the supplied single institutional page, one consultation."""
from datetime import date
from functools import partial
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from LoginRegister.access import require_capability
from .models import Atencion, Estudiante
from .pdf_reports import _fonts, _paragraph
from .reports import REPORT_ZONE
from .services import histories_for


def _validate(history):
    patient = history.estudiante
    missing = []
    for code, label in [('nombre', 'nombres'), ('apellido', 'apellidos'), ('cedula', 'cédula'),
                        ('sexo', 'sexo'), ('edo_civil', 'estado civil'), ('direccion', 'dirección'),
                        ('telefono', 'teléfono'), ('contacto_emergencia', 'contacto de emergencia')]:
        if not (getattr(patient, code) or '').strip():
            missing.append(label)
    for code, label in [('motivo_consulta', 'motivo de consulta'), ('enfermedad_actual', 'enfermedad actual'),
                        ('diagnostico_provisional', 'diagnóstico provisional'), ('diagnostico', 'diagnóstico de la consulta'),
                        ('tratamiento', 'tratamiento de la consulta')]:
        if not (getattr(history, code) or '').strip():
            missing.append(label)
    if not history.medico_id:
        missing.append('médico responsable registrado')
    if not isinstance(patient.fecha_nacimiento, date):
        missing.append('fecha de nacimiento')
    if not isinstance(history.fecha_consulta, date):
        missing.append('fecha de consulta')
    if missing:
        raise ValidationError('No se puede emitir FOR-SSS-04. Faltan: ' + ', '.join(missing) + '.')
    today = timezone.localdate(timezone=REPORT_ZONE)
    if patient.fecha_nacimiento > history.fecha_consulta or history.fecha_consulta > today:
        raise ValidationError('Las fechas de nacimiento y consulta no son coherentes. No se emitió el PDF.')
    if history.atencion_id and (history.atencion.paciente_id != patient.pk or history.atencion.estado != Atencion.Estado.ATENDIDO):
        raise ValidationError('La atención relacionada no corresponde al paciente o no está finalizada.')


def clinical_history_pdf(*, actor, history_id):
    require_capability(actor, 'export_clinical')
    history = histories_for(actor).select_related('medico', 'atencion').get(pk=history_id)
    _validate(history)
    _fonts()
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1)
    pdf.setTitle('Historia Clínica - FOR-SSS-04')
    pdf.setAuthor('UPTAG')
    paragraph = partial(_paragraph, pdf, page_size=A4)
    height = A4[1]
    pdf.setLineWidth(.45)
    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setFillColorRGB(0, 0, 0)
    logo = Path(settings.BASE_DIR) / 'base/static/base/img/logo_uptag_documentos.png'
    pdf.drawImage(str(logo), 36, height-106, width=220, height=73, preserveAspectRatio=True, mask='auto')
    paragraph('FOR-SSS-04', 475, 40, 87, 15, size=9, bold=True, center=True)
    paragraph('HISTORIA CLÍNICA', 150, 121, 295, 24, size=18, bold=True, center=True)
    # Positions and line counts measured directly from the supplied PDF.
    for x1, x2, top in [(87, 270, 163), (350, 553.2756, 163), (190, 553.2756, 198),
                        (70, 205, 230), (420, 553.2756, 230), (86, 160, 262),
                        (235, 310, 262), (442, 553.2756, 262), (118, 553.2756, 294),
                        (120, 553.2756, 326), (307, 553.2756, 358), (144, 275, 390), (383, 553.2756, 390)]:
        pdf.line(x1, height-top, x2, height-top)
    for label, x, top, width in [('FECHA:', 42, 153, 43), ('PNF:', 318, 153, 30),
            ('APELLIDOS Y NOMBRES:', 42, 188, 145), ('C.I.:', 42, 220, 26),
            ('LUGAR Y FECHA DE NACIMIENTO:', 225, 220, 193), ('EDAD:', 42, 252, 42),
            ('SEXO:', 188, 252, 45), ('ESTADO CIVIL:', 338, 252, 102),
            ('DIRECCIÓN:', 42, 284, 74), ('TELÉFONO:', 42, 316, 76),
            ('EN CASO DE EMERGENCIA AVISAR A:', 42, 348, 263),
            ('PARENTESCO:', 42, 380, 100), ('TELÉFONO:', 303, 380, 78)]:
        paragraph(label, x, top, width, 12, size=9.5)
    patient = history.estudiante
    birth, consultation = patient.fecha_nacimiento, history.fecha_consulta
    age = consultation.year - birth.year - ((consultation.month, consultation.day) < (birth.month, birth.day))
    values = [
        ('Fecha', consultation.strftime('%d/%m/%Y'), 90, 152, 177),
        ('PNF', patient.pnf if patient.tipo_paciente == Estudiante.Tipo.ESTUDIANTE else '', 353, 152, 197),
        ('Apellidos y nombres', f'{patient.apellido}, {patient.nombre}', 193, 187, 357),
        ('Cédula', patient.cedula, 73, 219, 129),
        ('Edad', str(age), 89, 251, 68), ('Sexo', patient.sexo, 238, 251, 69),
        ('Estado civil', patient.edo_civil, 445, 251, 105), ('Dirección', patient.direccion, 121, 283, 429),
        ('Teléfono', patient.telefono, 123, 315, 427),
        ('Contacto de emergencia', patient.contacto_emergencia, 310, 347, 240),
        ('Parentesco', patient.parentesco_emergencia, 147, 379, 125),
        ('Teléfono de emergencia', patient.telefono_emergencia, 386, 379, 164),
    ]
    for label, value, x, top, width in values:
        paragraph(value, x, top, width, 11, size=8.5, label=label)
    birthplace = patient.lugar_nacimiento.strip()
    birth_text = (birthplace+'\n' if birthplace else '') + birth.strftime('%d/%m/%Y')
    paragraph(birth_text, 423, 207 if birthplace else 219, 127, 22 if birthplace else 11,
              size=8.5, leading=10.5, label='Lugar y fecha de nacimiento')
    for label, text, title_top, first_line, count in [
            ('MOTIVO DE LA CONSULTA', history.motivo_consulta, 417, 448, 3),
            ('ENFERMEDAD ACTUAL', history.enfermedad_actual, 536, 567, 5),
            ('DIAGNÓSTICO PROVISIONAL', history.diagnostico_provisional, 709, 740, 3)]:
        paragraph(label, 45, title_top, 505, 17, size=11, bold=True)
        for index in range(count):
            top = first_line+27*index
            pdf.line(45, height-top, 550, height-top)
        paragraph(text, 48, first_line-14, 499, 27*count, size=10.5, leading=27, label=label)
    pdf.showPage()
    pdf.save()
    return stream.getvalue()
