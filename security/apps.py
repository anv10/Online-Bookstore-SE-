from django.apps import AppConfig


class SecurityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "security"
    verbose_name = "Security"

    def ready(self):
        from . import signals  # noqa: F401  (connects the auth signal receivers)
