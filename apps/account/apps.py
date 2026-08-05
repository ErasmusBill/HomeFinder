from django.apps import AppConfig


class AccountConfig(AppConfig):
    name = 'apps.account'
    label = 'user_account'

    def ready(self):
        # Import signals inside ready() and guard against import errors so that
        # a broken or missing signals module doesn't prevent Django from starting.
        try:
            from apps.account import signals  # noqa: F401
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Failed to import account signals: %s", e)
