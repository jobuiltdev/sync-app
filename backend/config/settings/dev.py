"""Local development settings.

Everything relaxed here is relaxed deliberately and only ever applies locally.
"""

from config.settings.base import *  # noqa: F403
from config.settings.base import REST_FRAMEWORK, SPECTACULAR_SETTINGS, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-local-development-only")

# A physical device reaches the development server by the machine's LAN address,
# which changes between networks. Accepting any host avoids hardcoding that IP,
# and applies only to this settings module.
ALLOWED_HOSTS = ["*"]

CORS_ALLOW_ALL_ORIGINS = True

# The browsable API is a convenience for poking at endpoints by hand locally.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
}

SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}
