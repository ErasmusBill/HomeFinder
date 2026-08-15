from django.apps import AppConfig


class TenantConfig(AppConfig):
    name = 'apps.tenant'

    def ready(self):
        import apps.tenant.signals
