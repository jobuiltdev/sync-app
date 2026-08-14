# Deploying Sync

What runs, what it needs, and what to do when something is wrong.

Nothing in this document has been exercised against a real hosting platform or a
real payment provider. It describes what the code requires and what has been
verified locally, which is a different thing from a deployment that has happened.

## Contents

1. [The processes](#1-the-processes)
2. [Configuration](#2-configuration)
3. [First deployment](#3-first-deployment)
4. [Migrations](#4-migrations)
5. [Health and readiness](#5-health-and-readiness)
6. [The webhook endpoint](#6-the-webhook-endpoint)
7. [Operating the money](#7-operating-the-money)
8. [Incidents](#8-incidents)
9. [Scaling](#9-scaling)
10. [What is not ready](#10-what-is-not-ready)

---

## 1. The processes

Three processes from one image, plus two managed services.

| Process | Command | How many |
| --- | --- | --- |
| API | `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --threads 2 --timeout 30` | As many as traffic needs |
| Worker | `celery -A config worker --loglevel=info --concurrency=4` | One or more |
| Scheduler | `celery -A config beat --loglevel=info` | **Exactly one** |

Plus PostgreSQL 17 and Redis 7, both managed rather than self-hosted unless
there is a reason otherwise.

**Exactly one scheduler.** Two beat processes queue every periodic task twice.
Every task is idempotent so nothing breaks, but it is twice the database load and
twice the calls to Paystack, and the duplication is invisible until somebody
looks at a provider's rate limit. If the platform cannot guarantee a single
instance, that is the thing to solve before launch.

The API and the worker can be scaled independently and should be. They fail for
different reasons and under different load.

### Why gunicorn with sync workers

This is a database-bound JSON API. An async worker class buys nothing until a
request path spends its time waiting on something external, and the one place
that happens, payment initialization, is already a single call. Three workers
with two threads each is a starting point, not a measured optimum; see
[scaling](#9-scaling).

## 2. Configuration

Everything comes from the environment. `.env.example` is the complete list with
notes on each; this is the subset that is **required in production**, where
missing means the process refuses to start.

| Variable | Notes |
| --- | --- |
| `DJANGO_SECRET_KEY` | 50+ characters, generated, never reused between environments |
| `DJANGO_ALLOWED_HOSTS` | The hostnames served. A wildcard is refused |
| `DATABASE_URL` | PostgreSQL. TLS is required by default, see `DATABASE_SSLMODE` |
| `REDIS_URL` | Cache |
| `CELERY_BROKER_URL` | Queue. Usually the same Redis, a different database number |
| `PAYMENT_GATEWAY` | `apps.payments.gateways.paystack.PaystackGateway` |
| `BANK_RESOLVER` | `apps.payments.banks.paystack.PaystackBankResolver` |
| `PAYOUT_TRANSFER_PROVIDER` | `apps.payments.transfers.paystack.PaystackTransferProvider` |
| `SMS_BACKEND` | `apps.accounts.sms.termii.TermiiSMSProvider` |
| `EMAIL_BACKEND` | `apps.accounts.email.resend.ResendEmailBackend` |
| `PAYSTACK_SECRET_KEY` | Required when any Paystack adapter is selected |
| `TERMII_API_KEY` | Required when the Termii adapter is selected |
| `RESEND_API_KEY` | Required when the Resend backend is selected |
| `DEFAULT_FROM_EMAIL` | Must be on a domain verified at Resend |

Optional in production: `DJANGO_CSRF_TRUSTED_ORIGINS` (needed for the admin
behind HTTPS), `DJANGO_CORS_ALLOWED_ORIGINS`, `DATABASE_SSLMODE`,
`DATABASE_CONN_MAX_AGE`, every `SCHEDULE_*` interval, `TASK_BATCH_SIZE`,
`PLATFORM_COMMISSION_RATE_BPS`, and the timeouts.

### What the process refuses to start with

`apps/common/checks.py` runs on every management command and every process
start. In production it is an error, not a warning, to have:

- any provider set to a fake, console or in-memory implementation
- a selected provider whose credential is empty
- `DEBUG` on, an empty or wildcard `ALLOWED_HOSTS`, or open CORS
- no `CELERY_BROKER_URL`
- a secret key that is short or contains `insecure`

It warns, rather than refusing, about no HSTS, no SSL redirect, insecure cookies,
and a `.env` file present in the image. Each of those has a legitimate reason to
be true behind particular infrastructure.

**Never put a `.env` file in a production image.** Environment variables win over
it, so it is not directly dangerous, but it will silently supply anything the
platform forgot to set, which turns a loud refusal into a quiet misconfiguration.
`.dockerignore` excludes it.

## 3. First deployment

```bash
# 1. Build. Nothing secret is needed or baked in.
docker build -t sync-api ./backend

# 2. Check the configuration before anything serves traffic. This runs the same
#    checks the process runs at startup, and fails loudly on anything missing.
docker run --rm --env-file <(your secret manager) sync-api \
    python manage.py check --deploy

# 3. Migrate. Once, from one place, before the new image serves.
docker run --rm --env-file <(...) sync-api python manage.py migrate

# 4. Start the three processes.
```

Create the first operator account with `manage.py createsuperuser`, run once
against the production database from a shell that has the environment.

## 4. Migrations

Run `migrate` once per deploy, before the new code serves traffic, from a single
place rather than from every starting container.

Every migration to date is additive: new tables, new nullable columns, new
constraints and indexes. None drops a column or a table, and none rewrites data.
`makemigrations --check` runs in CI, so a model changed without a migration fails
there rather than at the first request.

There is no development database reset anywhere in a production path. The only
`flush` or `drop` in this repository is Django's own test runner creating and
destroying its test database.

## 5. Health and readiness

| Endpoint | Answers | Use it for |
| --- | --- | --- |
| `/api/v1/health/live/` | Is the process running | Liveness probe, restart policy |
| `/api/v1/health/ready/` | Can it serve correctly | Readiness probe, load balancer |
| `/api/v1/health/` | The original combined check | Existing monitors, device connectivity |

**Point the liveness probe at `live/` and nothing else.** It touches no
dependency on purpose: a liveness probe that checks PostgreSQL restarts healthy
web processes every time the database hiccups, turning a small problem into an
outage.

Readiness checks the database, the cache, and whether the configuration is still
valid. It deliberately does **not** check Paystack, Termii or Resend: browsing,
booking, offers and job progress all work without them, and taking the whole
marketplace out of the load balancer because a payment provider is slow would be
a self-inflicted outage.

No health response contains a connection string, a driver message, a hostname or
a credential. Failures are a bare `"error"` and the detail goes to the logs.

## 6. The webhook endpoint

```
POST https://<your-host>/api/v1/webhooks/paystack/
```

Set it in the Paystack dashboard under Settings, API Keys and Webhooks. It must
be publicly reachable and HTTPS.

- Authenticated by an HMAC SHA-512 signature over the **raw request body**, using
  the same secret key as the API. There is no session and no token.
- An invalid or missing signature is `401` with the body `"Rejected."` and
  nothing is recorded.
- Everything past a valid signature answers `200`, including an event about a
  reference we never issued and one that arrives after the payment resolved. A
  provider that receives anything else retries, and retrying would not change
  either outcome.
- Events deduplicate on the provider's event id, so redelivery is safe.
- The payload is not stored. What is kept is the reference, amount, currency and
  a SHA-256 digest of the body.

If the platform sits behind a proxy that rewrites request bodies, the signature
will never match. That is the first thing to check if every webhook is refused.

## 7. Operating the money

Financial operations happen in the Django admin, by staff accounts.

**Who may do what.** Admin access requires `is_staff`, and each action requires
the relevant Django model permission. Grant `payments | payout request | Can
change` only to people who should be releasing money. There is no bypass around
the domain rules for anybody, superuser included: every admin action calls the
same guarded service functions the API and the tasks call, so an operator cannot
skip a lifecycle state, resurrect a terminal payout, or edit a settled amount.

**Releasing a payout.** A provider requests it; an operator selects it in
`Payout requests` and runs **Send the money (submits a real transfer)**. That
queues the same task everything else uses. There is no automatic payout anywhere
in this system: nothing pays anybody because earnings became available.

**A payout stuck in PROCESSING.** It has been submitted and we do not yet know
the outcome. Run **Ask the provider what happened**, which reconciles it. Never
try to send it again: the system refuses, and that refusal is the guarantee
against paying somebody twice. If reconciliation cannot resolve it, look the
transfer reference up in the Paystack dashboard.

**Anomalies.** `Financial anomalies` lists what the hourly consistency sweep
found and could not safely fix itself. Read it in the morning. `REPAIRED` entries
are closed already; `REVIEW` entries are waiting for a person and were
deliberately not touched.

## 8. Incidents

**Payments are not confirming.** Check the Paystack dashboard first. Payments
left `INITIALIZED` are reconciled every five minutes for seven days, so a
provider outage resolves itself once they recover. Nothing needs doing by hand
unless the anomaly list shows `UNRESOLVED_PAYMENT`.

**No background work is happening.** Offers not expiring and payments not
reconciling at the same time means the worker or the scheduler is down. Check
both. If the scheduler has been down, everything catches up on the next tick;
nothing is lost, because the work is derived from database state rather than from
queued messages.

**The database is unreachable.** Readiness goes red and instances leave the load
balancer; liveness stays green so nothing restart-loops. No data is at risk. When
it returns, connections are health-checked before reuse, so there is no wave of
stale-handle errors.

**A payout may have gone out twice.** It cannot have, through this system: a
payout carrying a transfer reference is never resubmitted by any path. Confirm by
looking the reference up at the provider. If a genuine duplicate exists, it came
from outside this system.

**Rolling back.** Deploy the previous image. Migrations are additive, so old code
runs against the new schema. Do not attempt to reverse a migration on a
production database with money in it.

## 9. Scaling

Current assumptions, and the first things that will break.

**Where it is fine today.** Every list endpoint is paginated. Every sweep is
bounded to `TASK_BATCH_SIZE`. Booking, offer, payment, settlement and payout
queries are all indexed on the columns they filter and order by. Offer
acceptance, payout requests and payout execution all serialise on a row lock and
are backed by database constraints rather than application checks.

**The first bottleneck: the derived balance.** `available_balance` aggregates a
provider's settlements and payouts on every read, and the earnings screen calls
it. It is indexed and correct, and it is O(number of settlements for that
provider). A provider with ten thousand completed jobs makes that query slow.
The fix when it arrives is a materialised balance updated by the same immutable
records, not a stored one that can drift; the derivation stays the source of
truth. Do not do this until a real provider is actually slow.

**The second: the consistency sweep.** It scans recent settlements and payments
hourly. Bounded per run, so it degrades into covering less rather than into
taking longer, but that means it eventually stops examining everything. Add a
`last_swept_at` cursor when that matters.

**N+1 risks.** The list endpoints use `select_related` for the joins they render.
The one to watch is the settlements list, which touches booking and service per
row; it is `select_related` today and should stay that way.

**What not to cache.** Anything financial. The earnings figure a provider sees
must be the one the server just computed, because a cached balance is how two
devices disagree about what can be withdrawn. The catalog is the opposite: it is
small, changes rarely and is read by everybody, and it is the first thing worth
caching when read volume justifies it.

**Connections.** `CONN_MAX_AGE` is ten minutes in production, so each worker
process holds a connection. The ceiling on PostgreSQL connections is API workers
times threads, plus Celery concurrency, plus one. Count it before scaling out;
it is the limit people hit first on managed PostgreSQL.

## 10. What is not ready

Honest list, as of M7.

- **No provider account is configured.** No real payment, SMS, email or transfer
  has ever been made by this system. Every adapter exists and every one is
  exercised against a deterministic fake.
- **No deployment has happened.** This document describes what the code requires.
  It has not been run on a hosting platform.
- **CI has never started.** See the CI section of `README.md`.
- **No error tracking.** Logs are structured JSON with correlation ids, which is
  enough to diagnose from a log aggregator, but nothing pages anybody.
- **No backups are configured here.** Managed PostgreSQL usually provides them;
  confirm the retention and, more importantly, test a restore.
- **The first real payout should be watched by a person**, start to finish, with
  the Paystack dashboard open.
