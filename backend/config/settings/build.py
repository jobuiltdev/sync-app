"""Settings for build-time tasks only.

`collectstatic` needs a settings module that imports, and production settings
deliberately refuse to import without a database URL, a secret key and real
provider credentials. None of those exist inside a container build, and none of
them should: a build must not be handed production secrets to copy the admin's
CSS into a directory.

So this module supplies throwaway values for the things Django insists on and
nothing else. **It is never used to serve traffic.** It cannot be: it has no real
database, and `IS_PRODUCTION` is false so none of the production checks would run
even if somebody pointed a process at it.
"""

from config.settings.base import *  # noqa: F403

DEBUG = False

SECRET_KEY = "build-time-only-never-used-to-serve-anything"
ALLOWED_HOSTS = []

# Never connected to. collectstatic touches no table.
DATABASES = {
    "default": {"ENGINE": "django.db.backends.postgresql", "NAME": "build-time-placeholder"}
}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}
