from .access import has_capability


def account_capabilities(request):
    return {'access': {name: has_capability(request.user, name) for name in (
        'read_clinical', 'write_clinical', 'export_clinical', 'manage_reposo', 'manage_patients', 'manage_attention', 'manage_accounts', 'view_reports',
    )}}
