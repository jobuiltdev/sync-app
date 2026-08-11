# Sync

A Nigerian everyday-services marketplace. Customers book dispatch, cleaning,
errands, home services, beauty and grooming, and laundry from one mobile app.
Providers receive and fulfil that work through the same app.

- `backend/` Django REST API
- `mobile/` Expo React Native app
- `docs/architecture.md` the architecture this implementation follows

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
│   │   └── common/         base model, error envelope, health endpoint
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

## Conventions

- Settings are split by environment. Secrets come from the environment, never from
  a settings file. `prod.py` reads required values without a fallback so a missing
  one stops the process rather than booting insecurely.
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
