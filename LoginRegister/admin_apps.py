from django.contrib.admin.apps import AdminConfig


class RestrictedAdminConfig(AdminConfig):
    default_site = 'LoginRegister.admin_site.AccountAdminSite'
