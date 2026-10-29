"""Pure renderer: FOR-SSS-07 from a fixed snapshot, without querying live data."""
from datetime import date
from functools import partial
from io import BytesIO
from pathlib import Path

from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics

from .pdf_reports import _fonts, _paragraph


CATEGORY_TEXT = {'estudiante': 'estudiante', 'profesor': 'profesor(a)',
                 'obrero_tecnico': 'integrante del personal obrero/técnico',
                 'administrativo': 'integrante del personal administrativo', 'externo': 'paciente externo'}
MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
          'septiembre', 'octubre', 'noviembre', 'diciembre')
TEMPLATE_REVISION = 'for-sss-07-dejavu-2.37-r2'


def render_reposo(snapshot, *, draft):
    _fonts()
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1)
    pdf.setTitle(f'Constancia de Reposo - FOR-SSS-07 - Versión {snapshot["numero_version"]}')
    pdf.setAuthor('UPTAG')
    paragraph = partial(_paragraph, pdf, page_size=A4)
    height = A4[1]
    pdf.setLineWidth(.45)
    pdf.drawImage(str(Path(settings.BASE_DIR) / 'base/static/base/img/logo_uptag_documentos.png'),
                  36, height-106, width=220, height=73, preserveAspectRatio=True, mask='auto')
    paragraph('FOR-SSS-07', 475, 40, 87, 15, size=9, bold=True, center=True)
    paragraph('CONSTANCIA DE REPOSO', 120, 121, 355, 25, size=18, bold=True, center=True)
    for x1, x2, y in [(74, 430, 233), (52, 543.2756, 312), (84, 255, 352),
                      (470, 543.2756, 352), (190, 247, 400),
                      *[(52, 543.2756, y) for y in [430, 466, 502, 538, 574]],
                      (398, 443, 640), (52, 240, 671), (300, 365, 671), (177, 418.2756, 802)]:
        pdf.line(x1, height-y, x2, height-y)
    paragraph('Yo', 52, 222, 20, 13, size=10.5)
    paragraph(snapshot['medico']['nombre_completo'], 77, 220, 350, 13, size=10.5, label='Nombre del médico')
    paragraph('médico al servicio', 440, 222, 105, 13, size=10.5)
    paragraph('de la UPTAG, hago constar que el (la) '+CATEGORY_TEXT[snapshot['paciente']['tipo_paciente']]+':',
              52, 262, 491, 25, size=10.5, label='Categoría del paciente')
    paragraph(snapshot['paciente']['nombre_completo'], 55, 298, 485, 13, size=10.5, label='Nombre del paciente')
    paragraph('C.I.:', 52, 341, 30, 13, size=10.5)
    paragraph(snapshot['paciente']['cedula'], 87, 339, 165, 13, size=10.5, label='Cédula')
    paragraph('PNF / Dependencia (si aplica):', 280, 341, 187, 13, size=10)
    pnf = snapshot['paciente']['pnf']
    pnf_two_lines = '\n' in pnf or pdfmetrics.stringWidth(pnf, 'UPTAG', 8.5) > 67
    paragraph(pnf, 473, 328 if pnf_two_lines else 339, 67, 22 if pnf_two_lines else 11,
              size=8.5, leading=10.5, label='PNF')
    paragraph('amerita reposo por', 52, 389, 136, 13, size=10.5)
    paragraph(str(snapshot['dias']), 193, 387, 51, 13, size=10.5, label='Días de reposo')
    paragraph('días, por presentar:', 255, 389, 250, 13, size=10.5)
    paragraph(snapshot['motivo_reposo'], 55, 416, 485, 180, size=11, leading=36, label='Motivo del reposo')
    issued = date.fromisoformat(snapshot['fecha_emision'])
    paragraph('Constancia expedida en Santa Ana de Coro, a los', 52, 629, 344, 13, size=10)
    paragraph(str(issued.day), 401, 627, 39, 13, size=10.5)
    paragraph('días del mes de', 450, 629, 94, 13, size=10)
    paragraph(MONTHS[issued.month-1], 55, 658, 182, 13, size=10.5)
    paragraph('del año', 250, 660, 48, 13, size=10.5)
    paragraph(str(issued.year), 303, 658, 59, 13, size=10.5)
    paragraph('Atentamente', 220, 756, 155, 15, size=11, center=True)
    paragraph('Médico responsable del Servicio Médico UPTAG', 150, 813, 295, 12, size=8.5, center=True)
    # The signature line remains blank. No simulated signature, seal or credential.
    if draft:
        pdf.saveState()
        pdf.translate(135, 365)
        pdf.rotate(34)
        pdf.setFillColorRGB(.7, .7, .7)
        pdf.setFont('UPTAG-Bold', 21)
        pdf.drawString(0, 0, 'BORRADOR - SIN APROBACIÓN')
        pdf.restoreState()
    pdf.showPage()
    pdf.save()
    return stream.getvalue()
