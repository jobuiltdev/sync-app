"""Project configuration.

Imports the Celery application so that `celery -A config` finds it and so that
`shared_task` registers against it. Building the app opens no connection and
runs nothing.
"""

from config.celery import app as celery_app

__all__ = ["celery_app"]
