from django.apps import AppConfig


class SubscriptionConfig(AppConfig):
    name = 'apps.Subscription'

    def ready(self):
        import apps.Subscription.signals  # noqa: F401 — registers cache-invalidation signals
