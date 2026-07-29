from django.apps import AppConfig


class HomeFinderConfig(AppConfig):
    name = 'apps.home_finder'

    def ready(self):
        import apps.home_finder.signals