# The API, the Celery worker and the Celery beat scheduler are the same image
# with different commands. One image means one dependency set to keep in step and
# one thing to build, and the three processes genuinely do run the same code.
#
# Two stages: dependencies are installed once into a virtual environment, and the
# runtime stage copies that environment without the build toolchain. The result
# has no compiler, no development dependencies, and nothing that can write to
# its own source.

# --- build -----------------------------------------------------------------
FROM python:3.14-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# psycopg[binary] ships wheels, and argon2-cffi needs a compiler only where a
# wheel is unavailable. Kept in the build stage either way so the runtime image
# carries neither.
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Dependencies before source, so a code change does not reinstall the world.
COPY pyproject.toml ./
RUN pip install --upgrade pip \
    # Runtime dependencies only. ruff, mypy and pytest have no business in a
    # production image.
    && pip install .

# --- runtime ---------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# Runs as nobody in particular, and owns nothing it could rewrite. A process that
# cannot modify its own code is one fewer thing an exploited dependency can do.
RUN useradd --create-home --uid 10001 sync

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY --chown=sync:sync . .

# The admin's own CSS and JavaScript, hashed and manifested at build time so the
# runtime image needs no write access and no build step. Collected with settings
# that need no database or secrets, since neither exists during a build.
RUN DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput

USER sync
EXPOSE 8000

# Liveness only. It answers without touching PostgreSQL or Redis, because a
# container that is alive but cannot reach its database should be taken out of
# the load balancer by the readiness probe, not restarted in a loop.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live/', timeout=4).status == 200 else 1)"

# Gunicorn with the default sync worker. This is a database-bound JSON API, and
# an async worker would buy nothing until there is something genuinely slow and
# external in a request path. Two threads per worker so a slow client cannot
# occupy a whole process.
#
# `--timeout 30` kills a request that hangs; nothing here should take that long,
# and a webhook that did would have been retried by the provider anyway.
#
# The other two processes run this same image with a different command:
#   worker: celery -A config worker --loglevel=info --concurrency=4
#   beat:   celery -A config beat --loglevel=info
# Exactly one beat process, ever. See docs/deployment.md.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "30", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
