from django.apps import AppConfig


class SubscriptionConfig(AppConfig):
    name = 'apps.Subscription'

    def ready(self):
        import apps.Subscription.views
