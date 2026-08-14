"""The Celery application.

Celery with Redis is what docs/architecture.md has specified since M0, and Redis
is already a dependency for the cache, so this adds a consumer of existing
infrastructure rather than a new piece of it.

**Importing this module starts nothing.** It builds an app object and registers
task modules. No connection is opened, no task runs, and `manage.py` behaves
exactly as it did. A worker is a separate process started deliberately.

The tasks themselves live beside the domains they act on, in each app's
`tasks.py`, for the same reason the capability policy lives in `accounts`: next
to the facts they read.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("sync")

# Every CELERY_ prefixed Django setting becomes Celery configuration, so there is
# one place configuration lives and it is the settings module like everything
# else.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Finds tasks.py in each installed app. Explicit over implicit would mean a list
# to forget to update.
app.autodiscover_tasks()
