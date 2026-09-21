from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = 'apps.common'

    def ready(self):
        # Patch the default admin.site.index to inject dashboard analytics.
        # This runs after autodiscover so all model registrations are intact.
        from apps.common.admin_site import patch_admin_site
        patch_admin_site()
