"""Stable storage codes; labels may change only after institutional confirmation."""

ADDITIONAL_OPTIONS = (('rp', 'RP'), ('t_de_c', 'T de C'))
PROCEDURE_OPTIONS = (('tto', 'Tto'), ('lab', 'Lab'), ('ref', 'Ref'),
                     ('imag', 'Imag'), ('rx', 'Rx'), ('cit', 'Cit'))
OPTION_GROUPS = (
    ('Datos adicionales del Registro Médico Diario', ADDITIONAL_OPTIONS),
    ('Estudios y procedimientos solicitados', PROCEDURE_OPTIONS),
)
OPTION_CODES = tuple(code for _, options in OPTION_GROUPS for code, _ in options)


def option_groups(history):
    return [(title, [{'code': code, 'label': label, 'value': getattr(history, code)}
                     for code, label in options]) for title, options in OPTION_GROUPS]
