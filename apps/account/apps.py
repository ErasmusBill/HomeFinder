from django.apps import AppConfig


class AccountConfig(AppConfig):
    name = 'apps.account'
    label = 'user_account'

    def ready(self):
        from apps.account import signals