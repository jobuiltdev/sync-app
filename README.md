# Sync

A Nigerian everyday-services marketplace. Customers book dispatch, cleaning,
errands, home services, beauty and grooming, and laundry from one mobile app.
Providers receive and fulfil that work through the same app.

- `backend/` Django REST API
- `mobile/` Expo React Native app
- `docs/architecture.md` the architecture this implementation follows
- `docs/deployment.md` what runs in production, and what to do when it breaks

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.14.6 | Django 5.2.17 LTS is pinned against it |
| Node.js | 24.x | npm 11.x |
| Docker Desktop | current | Provides PostgreSQL and Redis locally |

## First-time setup

### 1. Environment file

```bash
cp .env.example .env
```

Open `.env` and set `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`. `DATABASE_URL`
must agree with the `POSTGRES_*` values, because Docker Compose uses those to
create the database and Django uses the URL to connect to it.

Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

### 2. Infrastructure

```bash
docker compose up -d
docker compose ps
```

Both services should report `healthy`. PostgreSQL listens on 5432 and Redis on
6379, both configurable through `.env`.

### 3. Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate         # Windows
# source .venv/bin/activate    # macOS and Linux
pip install -e ".[dev]"
python manage.py migrate
```

### 4. Mobile

```bash
cd mobile
npm install
cp .env.example .env
```

Set `EXPO_PUBLIC_API_URL` in `mobile/.env`. See
[running on a physical device](#running-on-a-physical-device) for what to put
there.

## Running

### Backend

Bind to all interfaces so a phone on the same network can reach it:

```bash
cd backend
python manage.py runserver 0.0.0.0:8000
```

Check it:

```bash
curl http://127.0.0.1:8000/api/v1/health/
```

A healthy response is `200` with:

```json
{"status": "ok", "checks": {"database": "ok", "cache": "ok"}}
```

If a dependency is down the endpoint returns `503` and `"status": "degraded"`,
naming which check failed. The reason goes to the server log rather than the
response, since the endpoint is unauthenticated.

### Phone verification locally

Booking requires a verified phone number. Locally the console SMS provider prints
the code to the terminal running the server rather than sending a message:

```
[sms] verification code for +2348031234567: 481920
```

Set `SMS_BACKEND` in `.env` to change providers. No real provider is configured, so
no environment sends real SMS yet.

Also available in development:

- `/api/v1/schema/` OpenAPI document
- `/api/v1/docs/` Swagger UI
- `/admin/` Django admin

### Mobile

```bash
cd mobile
npm start
```

Press `a` for Android, `i` for iOS, or scan the QR code with a device.

## Running on a physical device

A phone cannot reach the development machine's `localhost`, so `EXPO_PUBLIC_API_URL`
must be the machine's LAN address. There is deliberately no localhost fallback in
the API client: a default that only fails on real hardware is the slowest possible
way to find this out.

**1. Find your LAN IP**

```bash
ipconfig                  # Windows, look for IPv4 Address on your active adapter
ifconfig | grep "inet "   # macOS and Linux
```

**2. Set it in `mobile/.env`**

```
EXPO_PUBLIC_API_URL=http://192.168.1.24:8000
```

Restart the Expo dev server afterwards. `EXPO_PUBLIC_*` values are read at bundle
time, so a running server will not pick up the change.

**3. Run Django on all interfaces**

`runserver 0.0.0.0:8000`, not the default `127.0.0.1:8000`.

**4. Allow the port through Windows Firewall**

Windows blocks inbound connections to Python by default, which presents as the app
timing out while the same URL works fine in a browser on the development machine.

A firewall rule only applies to the network profile it is scoped to, so check which
profile your active adapter is on first:

```powershell
Get-NetConnectionProfile | Select-Object InterfaceAlias, NetworkCategory
```

Then create the rule for that profile, in an elevated PowerShell:

```powershell
New-NetFirewallRule -DisplayName "Sync dev server" -Direction Inbound `
  -LocalPort 8000 -Protocol TCP -Action Allow -Profile Public
```

Substitute `Private` if that is what the previous command reported. Getting this
wrong is a silent failure: the rule is created, appears in the firewall list, and
does nothing.

Note that phone hotspots, cafes and airports all report Public, and Windows treats
Public as untrusted for good reason. Opening a port there exposes it to everyone on
that network. Remove the rule when you no longer need it:

```powershell
Remove-NetFirewallRule -DisplayName "Sync dev server"
```

**5. Confirm**

From the phone's browser, open `http://<your-lan-ip>:8000/api/v1/health/`. If that
returns JSON, the app will reach it too. If it does not, the problem is the network
or the firewall, not the app.

Both devices must be on the same network. Guest and client-isolation modes on many
routers block device-to-device traffic and will prevent this from working.

## Tests and checks

### Backend

```bash
cd backend
ruff check .              # lint
ruff format --check .     # formatting
mypy .                    # type check
pytest                    # tests
python manage.py check
python manage.py spectacular --file schema.yml --validate
```

Tests need PostgreSQL and Redis running, so start Docker Compose first.

### Mobile

```bash
cd mobile
npm run lint
npm run typecheck
npm test
```

## Project layout

```
sync-v1/
├── backend/
│   ├── config/
│   │   ├── settings/       base, dev, prod, test
│   │   ├── urls.py
│   │   └── api_v1.py       everything mounted under /api/v1/
│   ├── apps/
│   │   ├── common/         base model, error envelope, health endpoint
│   │   └── notifications/  what people are told, and how it got to them
│   └── pyproject.toml      dependencies and tool configuration
├── mobile/
│   ├── app/                expo-router routes
│   └── src/
│       ├── api/            client, error normalisation, endpoints
│       ├── components/ui/
│       ├── lib/            query client, secure storage
│       ├── state/          session store
│       └── theme/          design tokens
├── docs/architecture.md
├── docker-compose.yml
└── .github/workflows/
```

## The app

One Expo app, both roles. A provider is often also a customer, and one app lets a
person switch without reinstalling, which is why the provider surfaces sit beside
the customer ones on the home screen rather than behind a separate login.

| Screen | For |
| --- | --- |
| `home` | Browse the catalog, and every entry point below |
| `book/[slug]`, `bookings`, `booking/[id]` | Request a service, then follow it |
| `addresses` | Where work happens. The landmark matters more than the street |
| `verify-phone` | Both channels, phone and email |
| `pay/[id]` | Hosted checkout, then ask the server what happened |
| `provider` | Become a provider, list services and areas, take work on or off |
| `offers`, `offer/[id]` | Jobs offered to you, accept or decline |
| `jobs`, `job/[id]` | Work you took, and moving it forward |
| `earnings`, `payouts`, `payout/[id]`, `payout-request` | What you earned and getting paid |
| `payout-destination` | Your bank account, confirmed with the bank |

Two rules the app holds to. It renders what the server says is possible, reading
`allowed_transitions` and capability refusals rather than deciding for itself; and
it never computes money, because a balance the app worked out is a balance that
disagrees with the server the moment another device does anything.

## Background work

Two more processes, neither started by `runserver`. Nothing periodic happens
without them: offers never expire, payments are never reconciled, and payouts are
never sent.

```bash
cd backend
celery -A config worker --loglevel=info    # runs the tasks
celery -A config beat --loglevel=info      # queues the periodic ones
```

Exactly one scheduler, ever. Several workers is fine. Both need Redis, which
`docker compose up -d` already provides.

| Task | Every | What it does |
| --- | --- | --- |
| `expire_stale_offers` | 60s | Closes offers past their window, expires bookings nobody took |
| `reconcile_pending_payments` | 5m | Asks the gateway about payments that never resolved |
| `reconcile_payouts` | 5m | Resolves transfers whose outcome was never received |
| `retire_stale_challenges` | 1h | Retires verification challenges that can no longer be used |
| `sweep_financial_consistency` | 1h | Finds impossible financial states, repairs only the unambiguous |
| `deliver_notification` | on demand | Sends one message, retrying only what is worth retrying |

Without a worker, nothing is told to anybody. Bookings, payments and payouts all
still work correctly, because a notification is a side effect and never a source
of truth, but a provider will only find out about a job by opening the app.

## Notifications

Sync tells people what happened to their bookings, payments and payouts over the
same SMS and email providers verification uses. `docs/architecture.md` has the
full account; the parts worth knowing before touching any of it:

- **Domain code never names a vendor.** A booking service calls
  `notifications.booking_created(booking)`. Whether that becomes an SMS, an email
  or nothing is decided in `apps/notifications/`, and a test fails if `termii`,
  `resend` or `send_mail` appears in a lifecycle module.
- **A notification cannot fail a booking.** Everything is caught, including the
  queueing, and delivery is scheduled with `transaction.on_commit` so a rolled
  back transaction sends nothing.
- **A channel is only used when it is verified.** Sending a customer's address to
  an unverified number could hand it to a stranger. Those messages are recorded
  `SKIPPED` rather than dropped, so it is visible.
- **No message text is stored.** The row records the event, the recipient and the
  outcome. The message can be rendered again from the domain object.

Locally the console SMS provider and the console email backend print instead of
sending, so the whole path is exercisable with no account anywhere.

## Health

| Endpoint | Answers |
| --- | --- |
| `/api/v1/health/live/` | Is the process running. Touches nothing |
| `/api/v1/health/ready/` | Can it serve. Checks database, cache and configuration |
| `/api/v1/health/` | The original combined check |

## Production

`docs/deployment.md` is the full account. The short version:

- Three processes from one image: gunicorn, a Celery worker, one Celery beat.
- Configuration comes from the platform's environment, never from a `.env` in the
  image. `DJANGO_SETTINGS_MODULE=config.settings.prod`.
- The process **refuses to start** in production with a fake provider wired in, a
  missing credential for a provider it has selected, `DEBUG` on, a wildcard
  `ALLOWED_HOSTS`, no broker, or a development secret key.

Check a production configuration before deploying it:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy
```

**No provider account is configured, and nothing has been deployed.** Every
external integration runs against a deterministic fake. No real payment, SMS,
email or bank transfer has been made by this system.

## Continuous integration

**CI has never successfully started.** Every run since M0 ends in
`startup_failure` with zero jobs, and this is not a claim that CI passes.

The evidence, as of commit `a4b09a2`:

| Observation | Value |
| --- | --- |
| Push run | `31850016751`, `startup_failure`, 0 jobs |
| Manual dispatch of `backend` | `31844192696`, resolved `.github/workflows/backend.yml`, 1 second, 0 jobs |
| Manual dispatch of `ci-smoke` | `31850076408`, `startup_failure`, 1 second, 0 jobs |
| Workflow YAML | Parses locally; all three workflows registered and `active` |
| Actions | `enabled: true`, `allowed_actions: all` |
| Run annotations | None available (`404`) |

The last row of evidence is the decisive one. `.github/workflows/ci-smoke.yml` is
a single `echo`: no checkout, no services, no dependencies, nothing that could be
wrong with it. It fails at startup in one second with zero jobs, exactly like the
others, and GitHub resolved its path correctly before doing so.

**No workflow in this repository can start a job, whatever it contains.** That
rules out the YAML, the triggers, the services and the application entirely.

What to check outside the repository: the account's Actions billing and spending
limit, whether the account is in good standing, and whether any organisation or
enterprise policy blocks runners. None of that is visible through the API with
the current token scopes.

Locally, everything CI would run passes. Run it with:

```bash
cd backend && ruff check . && ruff format --check . && mypy . && pytest
cd mobile && npm run lint && npm run typecheck && npm test
```

## Conventions

- Settings are split by environment. Secrets come from the environment, never from
  a settings file. `prod.py` reads required values without a fallback so a missing
  one stops the process rather than booting insecurely, and `apps/common/checks.py`
  refuses at startup anything a missing variable would not catch.
- Every external provider is an interface with a real adapter and a deterministic
  fake. Development and tests use the fakes; production refuses them.
- Logs are JSON in production and carry a request id. Nothing logs a password, a
  verification code, a token, an account number or a provider key.
- Domain models inherit `apps.common.models.BaseModel`, which gives them a UUID
  primary key and created and updated timestamps.
- Money is stored as an integer number of kobo, never a float.
- API errors all use one envelope, `{"error": {"code", "message", "details"}}`.
  `code` is stable and is what the app branches on.
- Endpoints are private by default. Public routes declare `AllowAny` explicitly, so
  a forgotten permission fails closed.
- Mobile native module versions come from the Expo SDK manifest. Install them with
  `npx expo install`, never `npm install`, because the SDK manifest and npm latest
  disagree for several packages.
