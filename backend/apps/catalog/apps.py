from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"

    def ready(self) -> None:
        # Registered here so every entry point (API, admin, shell, tests) sees the
        # same set of specs without each having to remember to load them.
        from apps.catalog import specs

        specs.load_specs()
