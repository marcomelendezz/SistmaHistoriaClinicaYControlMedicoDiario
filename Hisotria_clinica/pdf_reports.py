"""FOR-SSS-02: selectable text, 17 rows, explicit clinical option marks."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.exceptions import ValidationError
import reportlab
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from .reports import daily_report


PAGE_SIZE = landscape(A4)
ROWS_PER_PAGE = 17
# Coordinates measured from the supplied institutional A4 landscape reference.
COLUMN_EDGES = (32, 58.02605, 85.01603, 233.4609, 317.3226, 351.0601,
                379.014, 406.9679, 469.6232, 630.5992, 660.4809, 690.3627,
                720.2445, 750.1262, 780.008, 809.8898)
OPTION_COLUMNS = {'rp': 1, 't_de_c': 6, 'tto': 9, 'lab': 10,
                  'ref': 11, 'imag': 12, 'rx': 13, 'cit': 14}
TABLE_TOP, HEADER_HEIGHT, ROW_HEIGHT = 215, 44, 16
HEADINGS = ('N.º', 'Rp', 'Apellidos y nombres', 'Cédula de<br/>identidad', 'Edad',
            'Sexo', 'T.C.', 'Especialidad', 'Diagnóstico', 'Tto', 'Lab', 'Ref', 'Imag', 'Rx', 'Cit')


def _fonts():
    # DejaVu extends Vera with Greek/subscripts. Vendored with its embedded license.
    root = Path(reportlab.__file__).resolve().parent / 'fonts'
    if 'UPTAG' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('UPTAG', str(Path(settings.BASE_DIR) / 'base/static/base/fonts/DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont('UPTAG-Bold', str(root / 'VeraBd.ttf')))


def _paragraph(pdf, text, x, top, width, height, *, size=7.5, bold=False, center=False, label='Texto', markup=False,
               page_size=PAGE_SIZE, leading=None):
    if text is None or text == '':
        return
    text = str(text)
    if any(ord(char) < 32 and char not in '\n\r\t' for char in text):
        raise ValidationError(f'{label}: contiene caracteres no imprimibles.')
    font_name = 'UPTAG-Bold' if bold else 'UPTAG'
    glyphs = pdfmetrics.getFont(font_name).face.charToGlyph
    missing = sorted({ord(char) for char in text if char not in '\n\r\t' and ord(char) not in glyphs})
    if missing:
        points = ', '.join(f'U+{point:04X}' for point in missing[:5])
        raise ValidationError(f'{label}: la fuente no admite {points}. No se sustituyó ni recortó el contenido.')
    style = ParagraphStyle('cell', fontName=font_name, fontSize=size,
                           leading=leading if leading is not None else size + 1, alignment=1 if center else 0,
                           spaceBefore=0, spaceAfter=0, splitLongWords=True)
    paragraph = Paragraph(text if markup else escape(text).replace('\n', '<br/>'), style)
    _, used = paragraph.wrap(width, height)
    if used > height + .01:
        raise ValidationError(f'{label}: el texto no cabe en el formato institucional. No se ha recortado ni emitido el PDF.')
    paragraph.drawOn(pdf, x, page_size[1] - top - used)


def _page(pdf, day, team, rows, number, page_count):
    height = PAGE_SIZE[1]
    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setLineWidth(.45)
    logo = Path(settings.BASE_DIR) / 'base/static/base/img/logo_uptag_documentos.png'
    pdf.drawImage(str(logo), 36, height-106, width=220, height=73, preserveAspectRatio=True, mask='auto')
    _paragraph(pdf, 'FOR-SSS-02', 720, 40, 87, 15, size=9, bold=True, center=True)
    _paragraph(pdf, 'REGISTRO MÉDICO DIARIO', 250, 120, 400, 24, size=18, bold=True, center=True)
    for x1, x2, y in [(76, 215, 169), (355, 560, 169), (612, 806.8898, 169),
                      (78, 217, 196), (311, 806.8898, 196)]:
        pdf.line(x1, height-y, x2, height-y)
    for label, x, y, width in [('Fecha:', 34, 160, 40), ('Nombre del médico:', 232, 160, 120),
                                ('C.I.:', 578, 160, 30), ('Turno:', 34, 187, 40),
                                ('Enfermera:', 232, 187, 75)]:
        _paragraph(pdf, label, x, y, width, 12, size=9)
    _paragraph(pdf, day.date.strftime('%d/%m/%Y'), 79, 159, 132, 10, label='Fecha')
    if team:
        _paragraph(pdf, str(team.doctor), 358, 159, 198, 10, label='Nombre del médico')
        _paragraph(pdf, team.shift, 81, 186, 132, 10, label='Turno')
        _paragraph(pdf, str(team.nurse) if team.nurse else '', 314, 186, 488, 10, label='Enfermera')
    # C.I. of doctor and specialty remain blank: these data are not stored.
    bottom = TABLE_TOP + HEADER_HEIGHT + (ROWS_PER_PAGE + 1) * ROW_HEIGHT
    for x in COLUMN_EDGES:
        pdf.line(x, height-TABLE_TOP, x, height-bottom)
    for y in [TABLE_TOP, TABLE_TOP+HEADER_HEIGHT, *[TABLE_TOP+HEADER_HEIGHT+i*ROW_HEIGHT for i in range(1, ROWS_PER_PAGE+2)]]:
        pdf.line(COLUMN_EDGES[0], height-y, COLUMN_EDGES[-1], height-y)
    for index, heading in enumerate(HEADINGS):
        x, right = COLUMN_EDGES[index:index+2]
        _paragraph(pdf, heading, x+2, TABLE_TOP+12, right-x-4, 25, size=6.8, bold=True, center=True, markup=True)
    _paragraph(pdf, 'F / M', COLUMN_EDGES[5]+2, TABLE_TOP+33, COLUMN_EDGES[6]-COLUMN_EDGES[5]-4, 9, size=6, center=True)
    _paragraph(pdf, 'P / S', COLUMN_EDGES[6]+2, TABLE_TOP+33, COLUMN_EDGES[7]-COLUMN_EDGES[6]-4, 9, size=6, center=True)
    for index in range(ROWS_PER_PAGE):
        top = TABLE_TOP + HEADER_HEIGHT + index*ROW_HEIGHT + 3
        _paragraph(pdf, f'{index+1:02}', COLUMN_EDGES[0]+2, top, COLUMN_EDGES[1]-COLUMN_EDGES[0]-4, 11, center=True)
        if index >= len(rows):
            continue
        row = rows[index]
        patient, history = row['attention'].paciente, row['history']
        values = {2: f'{patient.apellido}, {patient.nombre}', 3: patient.cedula,
                  4: '' if row['age'] is None else str(row['age']),
                  5: {'Femenino': 'F', 'Masculino': 'M'}.get(patient.sexo, ''), 8: history.diagnostico}
        for code, column in OPTION_COLUMNS.items():
            values[column] = 'X' if getattr(history, code) is True else ''
        for column, value in values.items():
            x, right = COLUMN_EDGES[column:column+2]
            _paragraph(pdf, value, x+3, top, right-x-6, 11,
                       center=column in [1, 4, 5, 6, 9, 10, 11, 12, 13, 14],
                       label=f'Consulta {history.pk}, {HEADINGS[column].replace("<br/>", " ")}')
    _paragraph(pdf, 'Total', COLUMN_EDGES[0]+2, bottom-ROW_HEIGHT+3, COLUMN_EDGES[2]-COLUMN_EDGES[0]-4, 11, size=7, bold=True)
    _paragraph(pdf, str(len(rows)), COLUMN_EDGES[2]+3, bottom-ROW_HEIGHT+3, 100, 11, bold=True)
    _paragraph(pdf, f'Hoja {number} de {page_count}', 680, 567, 127, 10, size=7, center=True)
    pdf.showPage()


def daily_register_pdf(*, actor, start, end):
    # Both direct service calls and HTTP downloads enforce current permissions.
    report = daily_report(actor=actor, start=start, end=end)
    if report.excluded_count:
        raise ValidationError('Hay atenciones inconsistentes en el rango. Revisa las advertencias del diario antes de emitir el PDF.')
    _fonts()
    pages = []
    for day in report.days:
        if not day.teams:
            pages.append((day, None, []))
        for team in day.teams:
            for offset in range(0, len(team.rows), ROWS_PER_PAGE):
                pages.append((day, team, team.rows[offset:offset+ROWS_PER_PAGE]))
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=PAGE_SIZE, pageCompression=1)
    pdf.setTitle('Registro Médico Diario - FOR-SSS-02')
    pdf.setAuthor('UPTAG')
    for index, (day, team, rows) in enumerate(pages, start=1):
        _page(pdf, day, team, rows, index, len(pages))
    pdf.save()
    return stream.getvalue()
