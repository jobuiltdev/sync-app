from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    label = "common"

    def ready(self) -> None:
        """Registers the production configuration checks.

        Importing the module is what registers them, and they run wherever
        Django's check framework runs: manage.py check, migrate, runserver, and a
        Celery worker through its Django fixup. Outside production every one of
        them returns immediately.
        """
        from apps.common import checks  # noqa: F401
