# Sync architecture

Sync is a Nigerian everyday-services marketplace. Customers book across six
categories (dispatch, cleaning, errands, home services, beauty and grooming, and
laundry) from one mobile application, and providers receive and fulfil that work
through the same app.

This document is the reference the implementation follows. It records what was
decided and, where the reasoning is not obvious from the code, why.

## Contents

1. [Settled decisions](#1-settled-decisions)
2. [System architecture](#2-system-architecture)
3. [Identity and progressive verification](#3-identity-and-progressive-verification)
4. [Mobile architecture](#4-mobile-architecture)
5. [Django architecture](#5-django-architecture)
6. [Domain models](#6-domain-models)
7. [API structure](#7-api-structure)
8. [Navigation structure](#8-navigation-structure)
9. [Design system](#9-design-system)
10. [Milestones](#10-milestones)
11. [Risks and open decisions](#11-risks-and-open-decisions)

---

## 1. Settled decisions

| Area | Decision |
| --- | --- |
| Runtime | Python 3.14.6, Django 5.2.17 LTS |
| Layout | Monorepo, `backend/` and `mobile/` side by side |
| Identity | Email and password, plus Google. Multiple auth methods per account |
| Verification | Progressive, separate from authentication, enforced server-side |
| Matching | Hybrid: automatic broadcast by default, customer may request a provider |
| Money | Integer kobo in `BigIntegerField` |
| Identity documents | No full NIN or BVN stored. External check, result only |
| Admin | Django admin for Phase 1 |

### Why Django 5.2 LTS rather than 6.1

A compatibility spike built the full dependency set on Python 3.14.6 against both
Django 6.1 and Django 5.2.17. Both installed cleanly and both passed a smoke test
covering DRF, SimpleJWT and drf-spectacular. The difference is in what the
maintainers declare:

| Library | Version | Declares Django 6.1 | Declares Django 5.2 |
| --- | --- | --- | --- |
| djangorestframework | 3.18.0 | yes | yes |
| drf-spectacular | 0.30.0 | no, tops out at 6.0 | yes |
| djangorestframework-simplejwt | 5.5.1 | no, tops out at 5.2 | yes |

Both lagging libraries carry open-ended requirements, which is why they run on 6.1
despite not claiming it. They are untested there rather than incompatible. Django
5.2 is supported until April 2028, which covers the build and the first year after
launch with no forced framework upgrade, and nothing in this design needs a 6.x
feature. SimpleJWT does not list Python 3.14 in its classifiers; it is pure Python
over PyJWT, it was verified working during the spike, and that gap is accepted.

---

## 2. System architecture

One Django REST API serving three audiences (customer app, provider surfaces,
admin), one Expo app containing both role experiences, and external services each
hidden behind an internal adapter so none of them leak into domain code.

```
sync-v1/
├── backend/
│   ├── manage.py
│   ├── config/            settings/{base,dev,prod,test}.py, urls, api_v1, asgi, wsgi
│   ├── apps/              domain apps
│   └── pyproject.toml     dependencies, ruff, mypy, pytest, coverage
├── mobile/
│   ├── app/               expo-router routes
│   └── src/               api, features, components, theme, lib, state
├── docs/
├── .github/workflows/
└── docker-compose.yml     local PostgreSQL and Redis
```

### The one workflow everything runs through

Every category moves through the same sequence. The verticals differ only in what
they collect up front and how they price it.

```
DRAFT -> QUOTED -> PENDING_PAYMENT -> MATCHING -> ASSIGNED
      -> [EN_ROUTE] -> IN_PROGRESS -> AWAITING_CONFIRMATION -> COMPLETED

MATCHING -> EXPIRED            no provider found
* -> CANCELLED                 by customer, provider or admin
COMPLETED -> DISPUTED
```

`EN_ROUTE` is optional and declared per service by its spec.

### Booking, as implemented

The lifecycle above is the full canonical set. The implemented subset is
everything a booking reaches without quoting or payment:

```
MATCHING -> ASSIGNED -> [EN_ROUTE] -> IN_PROGRESS
         -> AWAITING_CONFIRMATION -> COMPLETED

MATCHING -> EXPIRED      every offer declined or lapsed
MATCHING, ASSIGNED, EN_ROUTE -> CANCELLED
```

`EN_ROUTE` is optional because `ASSIGNED` reaches `IN_PROGRESS` directly, so a
service with no travel step never uses it. No per-service flag is needed.

**Actors are part of the table, not just edges.** Only a provider moves work
forward; only a customer confirms it is done. A provider closing their own job
would make the confirmation meaningless. `apps/bookings/state.py` holds the whole
table, and `services.transition()` is the only way a status changes: the API never
accepts a status from a client, every move is a named action endpoint, and an
illegal one returns `ILLEGAL_TRANSITION` with the booking untouched.

**A booking starts MATCHING.** It is a request until a provider takes it, and the
only route to `ASSIGNED` is an accepted offer, which the offer domain drives as
`SYSTEM`. No human actor can move a booking into `ASSIGNED` directly.

**The address is copied, not referenced.** A booking records where a job was
requested. An `Address` is a mutable row a customer edits or deletes freely, so
pointing at it would mean a completed job silently moves house when they update
their flat number. The snapshot carries street, landmark, area, LGA, state,
coordinates and directions. `source_address` keeps the link and is allowed to go
null. Verified live: editing and deleting the source leave the booking intact.

**`details` is validated against the spec registered for the chosen service**, and
`spec_key` is copied onto the booking so the payload stays interpretable if the
Service is later repointed. A payload valid for laundry is not a valid cleaning
request, and that is enforced at creation.

**Booking requires a verified phone.** The rule lives in `apps/accounts/policy.py`
as `Capability.CREATE_BOOKING -> [PHONE_VERIFIED]`, checked before any write, so a
refusal persists nothing. Email verification is deliberately not required: a
provider on their way needs to reach the customer by phone, and demanding both
costs conversion at the moment of commitment. M4 and M5 add capabilities to the
same table without touching the booking domain.

**Deletion.** `customer`, `provider` and `service` are all `PROTECT`. A booking is
a record of something that happened between two people and must outlive a profile
tidy-up, so an account with bookings is deactivated rather than deleted.

Deferred from the booking domain, with the milestone that owns each: quotes and
pricing (M5), availability windows (later), the `Cancellation` model with fees
(M5), `DISPUTED` (M7), and `DRAFT` / `QUOTED` / `PENDING_PAYMENT`, which are
defined above but have no meaning until the milestones that produce them exist.

### Offers and acceptance, as implemented in M4

A booking opens in `MATCHING` and reaches `ASSIGNED` only through an accepted
offer. A request is not work until somebody has taken it.

**Dispatch has no ranking.** Eligibility is a filter over facts already recorded
in M2: the provider offers the service and that offering is active, their
verification status is `APPROVED`, their own `is_accepting_jobs` switch is on, and
they cover the booking's state. Every eligible provider is offered the job at the
same moment and the first to accept wins. A scoring or pool-widening strategy is a
later decision, and inventing one now would bury a business rule nobody agreed on.

**Naming a provider is still supported**, which is the hybrid matching decision in
section 1. A named provider gets a single `DIRECT` offer and is held to exactly the
same eligibility bar: being asked for by name is not a way past approval.

**Offer lifecycle**, an explicit status like every other lifecycle here:

```
PENDING -> ACCEPTED     this provider took it
        -> DECLINED     this provider turned it down
        -> EXPIRED      the window closed unanswered
        -> SUPERSEDED   somebody else took the booking first
```

Every terminal state is terminal. `SUPERSEDED` is deliberately distinct from
`DECLINED`: the provider did nothing wrong and their acceptance rate should not
record a refusal for a job somebody else was quicker on.

**The concurrency invariant is enforced by the database, not by application
checks.** A partial unique index permits at most one `ACCEPTED` offer per booking,
so even if two transactions both passed an application-level test only one can
commit. On top of that, acceptance locks the booking row with `select_for_update`,
which makes the race deterministic rather than merely safe: the loser waits, sees
the booking is no longer `MATCHING`, and is told the job is gone. Verified against
a real database with two concurrent threads: one winner, one accepted offer, one
`ASSIGNED` event, no offers left pending.

**A provider is never told who beat them.** Losing an offer returns
`BOOKING_NO_LONGER_AVAILABLE` with no detail, because which competitor took a job
is not information a provider is owed.

**When every offer is declined the booking becomes `EXPIRED`**, which is what the
lifecycle above already defines for a request no provider took. Declining touches
only that provider's own offer and never the customer's booking directly.

**Accepting requires more than booking does.** `ACCEPT_JOB` needs both
`PHONE_VERIFIED` and `EMAIL_VERIFIED`, against `CREATE_BOOKING`'s phone alone. A
provider is going into somebody's home, so both contact channels are proven: the
phone so the customer can reach them on the day, the email as a second and harder
to churn identifier for the account behind the work. Declining requires neither,
since turning work down is not entering anyone's home.

Note that eligibility reads the **provider profile**, not the user's contact
verification. An unverified provider can still receive offers and will be told to
verify when they try to accept, which is a prompt rather than a dead end. It does
mean a booking can be held open by someone who cannot yet accept, which the offer
expiry bounds.

Deferred: offer waves and pool widening, ranking, availability windows, and any
automatic re-dispatch after a decline.

### How verticals stay modular

This is the load-bearing idea. The `Booking` model never learns the vocabulary of
any single vertical. It carries a validated `details` JSON payload, and each
service registers a **service spec** in code that owns three things: the
serializer that validates and shapes `details`, the pricing function that turns
`details` into a priced quote breakdown, and the declaration of which optional
lifecycle states apply.

```
backend/apps/catalog/specs/
├── base.py          ServiceSpec: details_serializer, quote(), status_flow(), summary()
├── registry.py      register(spec) / get(spec_key), loaded at app ready
├── dispatch.py      pickup, dropoff, package size   -> distance pricing
├── cleaning.py      property type, rooms, depth      -> size and duration pricing
├── errands.py       task list, budget cap            -> time plus reimbursement
├── home_services.py trade, problem, inspect first    -> callout plus quote-on-site
├── beauty.py        treatments, at-home or in-salon  -> per-treatment fixed
└── laundry.py       item counts, wash type, express  -> per-item pricing
```

Adding a seventh category is a new spec module plus a `Service` row. It requires no
migration on `bookings`, no change to the state machine, no change to payments, and
no change to the mobile booking shell. That is the test the architecture has to
keep passing.

A table per vertical (`DispatchDetail`, `CleaningDetail`) would give stronger
typing, but it makes every new category a schema migration and pushes vertical
knowledge into core queries and serializers. A validated JSON payload behind a
code-owned serializer keeps validation strict while keeping the core closed to
modification.

### External services

| Concern | Choice | Boundary |
| --- | --- | --- |
| Payments | Paystack (cards, transfer, USSD) | `payments/gateways/base.py` |
| Payouts | Paystack Transfers | `wallets/payouts/base.py` |
| Transactional email | Resend or AWS SES | `notifications/email/base.py` |
| SMS | Termii, with a fallback provider | `notifications/sms/base.py` |
| Identity verification | Prembly, Youverify or VerifyMe | `providers/identity/base.py` |
| Google sign-in | ID token verified with `google-auth` | `accounts/social/google.py` |
| Push | Expo Push | `notifications/push/base.py` |
| Media and documents | S3 compatible, private ACL | django-storages |
| Background work | Celery with Redis | offers, payouts, webhooks, notifications |

Celery is the one piece of infrastructure introduced ahead of proven need, because
the matching engine requires it: an offer that expires after 45 seconds and widens
the pool is a scheduled job, not a request cycle.

---

## 3. Identity and progressive verification

Three things that are easy to conflate are kept strictly apart. Conflating them
produces both the giant onboarding wall and the unhelpful authorization error.

| Concept | Question it answers | Where it lives |
| --- | --- | --- |
| Authentication | Can you prove you hold this account? | Password, or a Google identity |
| Account verification | Do these contact channels belong to you? | `email_verified_at`, `phone_verified_at` |
| Provider verification | Should we let this person into a customer's home? | A reviewed, staged lifecycle |

A user can be fully authenticated and entirely unverified. That state is
legitimate: browse services, browse providers, read service information, explore
the app, manage permitted profile fields. Verification is demanded only where it
matters.

### Progressive verification, not a wall

Registration ends with "Your account is ready", not a queue of screens. The account
tab carries a checklist (account created, verify email, verify phone) the customer
completes whenever they like. When they attempt something that requires more, the
app explains exactly what is needed and offers the flow inline.

The API is the enforcement layer, always. The mobile app mirrors the rules so the
experience is honest rather than trial and error, but every gated operation is
checked server-side on every request.

### Capabilities, not endpoint-by-endpoint checks

Gated operations are named as capabilities and mapped to requirements in one policy
module, so the API, the admin, and any future client agree on what is blocked.

```python
# apps/accounts/policy.py

CAPABILITY_REQUIREMENTS = {
    Capability.CREATE_BOOKING:  [EMAIL_VERIFIED, PHONE_VERIFIED],
    Capability.MAKE_PAYMENT:    [EMAIL_VERIFIED, PHONE_VERIFIED],
    Capability.LEAVE_REVIEW:    [EMAIL_VERIFIED],
    Capability.ACCEPT_JOB:      [EMAIL_VERIFIED, PHONE_VERIFIED, PROVIDER_APPROVED],
    Capability.REQUEST_PAYOUT:  [EMAIL_VERIFIED, PHONE_VERIFIED, PROVIDER_APPROVED,
                                 PAYOUT_ACCOUNT_VERIFIED],
}
```

A service may demand more than the global policy, never less, through
`Service.additional_requirements`. Dispatch and errands carry higher abuse risk and
escalate.

Enforcement runs in two places on purpose: a DRF permission class guards the view,
and the underlying service function re-checks before it acts, so an admin action or
a background task cannot quietly route around the policy. Both call the same
`policy.check(user, capability)`, which returns the unmet requirements rather than a
bare boolean.

### The error contract

A blocked request names the requirement, states what is already satisfied, and
tells the client which call unblocks it.

```json
HTTP 403
{
  "error": {
    "code": "PHONE_VERIFICATION_REQUIRED",
    "message": "Verify your phone number to book a service.",
    "details": {
      "capability": "CREATE_BOOKING",
      "unmet": ["PHONE_VERIFIED"],
      "satisfied": ["EMAIL_VERIFIED"],
      "next_step": {
        "requirement": "PHONE_VERIFIED",
        "action": "POST /api/v1/auth/phone/verification/request",
        "has_phone_on_file": true
      }
    }
  }
}
```

| Code | Meaning |
| --- | --- |
| `EMAIL_VERIFICATION_REQUIRED` | Email is the only unmet requirement |
| `PHONE_VERIFICATION_REQUIRED` | Phone is the only unmet requirement |
| `PROVIDER_VERIFICATION_REQUIRED` | Provider is not in the approved state |
| `VERIFICATION_REQUIRED` | Several unmet. `details.unmet` lists them in ask order |

### One account, several ways in

| Situation on Google sign-in | Outcome |
| --- | --- |
| Google subject id already on a `SocialAccount` | Log in as that user |
| No subject match, email matches a user, Google reports the email verified | Link automatically, and stamp `email_verified_at` if it was unset |
| No subject match, email matches a user, Google does **not** report it verified | Refuse to link. Require password login first, then link from settings |
| No match at all | Create the account with `email_verified_at` set and no usable password |

The third row is the account-takeover guard: auto-linking on an unverified provider
email lets an attacker register a social identity carrying someone else's address
and inherit their account. The ID token is verified server-side against Google's
keys and audience, and `email_verified` is a hard gate rather than a hint.

Unlinking applies the same principle in reverse. A user cannot remove their last
remaining way in, so a Google-only account must set a password first.

### Verification challenges, as implemented

`VerificationChallenge` carries a `channel`, so email verification is a new row
rather than a second verification architecture. Only PHONE is wired up.

**The flow.** `PUT /auth/phone/` sets the number, `POST /auth/phone/verification/
request/` sends a code, `POST /auth/phone/verification/confirm/` submits it. Only a
correct code sets `phone_verified_at`; no endpoint, serializer or admin field
writes it, because a customer declaring their own phone verified would make the
booking gate decorative.

**Only a hash is stored**, produced by the project's configured password hashers,
so today that is Argon2. An earlier revision of this document specified a keyed
HMAC, reasoning that a six digit code has too little entropy for slow hashing to
add much and that hashing on every attempt is a deliberate CPU cost. That cost is
real and is now bounded by the per-challenge attempt cap, the resend cooldown and
DRF throttles on both endpoints. Reusing the established hashing infrastructure was
preferred over a bespoke scheme.

**The code exists in plaintext only inside the request that generates it**, on its
way to the provider. It is never persisted, never returned by the API, and never
logged.

- **Attempt cap** of five per challenge, after which it is burned. The failure is
  raised after the transaction commits, so a wrong guess durably increments the
  counter rather than rolling it back.
- **Expiry** of ten minutes, with a sixty second resend cooldown.
- **Rate limits**: the cooldown is per destination, so changing your number lets
  you request for the new one immediately while one number cannot be spammed. The
  hourly send limit is per account, so rotating numbers is not a way around it.
  All of it is database backed and works with Redis unavailable.
- **Supersession**: a new challenge retires the previous one, so only one code is
  ever live.
- **The destination is snapshotted.** A challenge is bound to the number it was
  sent to, which is what stops a code for an old number verifying a new one.
- **Changing the phone clears `phone_verified_at`**, enforced on the model itself
  so the invariant holds for the admin and the shell, not only the API.

**SMS provider.** The domain depends on `SMSProvider.send_verification_code` and
never on a vendor. `ConsoleSMSProvider` is the development default and prints the
code to stdout rather than the logger, since logs get shipped and retained.
`LocMemSMSProvider` records messages in memory for tests. **No production provider
is configured.** Setting `SMS_BACKEND` to a real one is a prerequisite for launch,
and until then no real SMS is sent by any environment.

### Provider verification

```
PENDING -> UNDER_REVIEW -> APPROVED
                        -> REJECTED -> UNDER_REVIEW   (resubmitted)
APPROVED -> SUSPENDED -> APPROVED                     (reinstated)
```

Independent of email and phone verification, which are prerequisites rather than
stages. Onboarding is a server-computed checklist so the app never infers progress.
Each resubmission creates a new record rather than overwriting, so rejection history
survives.

The identity check runs at a licensed provider. Sync keeps the outcome, the vendor
reference, the method used, the timestamp, and a masked last four digits for support
conversations. Holding full NIN or BVN values would add real NDPR exposure and buy
nothing the reference does not already give us.

---

## 4. Mobile architecture

One Expo app, two role experiences, separated by expo-router route groups rather
than two binaries. A provider is often also a customer, and one app lets a person
switch without reinstalling.

```
mobile/
├── app/                     routes only, thin. Screens compose features
│   ├── _layout.tsx          providers, fonts, session gate
│   ├── (auth)/
│   ├── (customer)/
│   └── (provider)/
└── src/
    ├── api/                 client, generated types, endpoints per domain
    ├── features/            auth, verification, catalog, booking, tracking, wallet
    ├── components/ui/       Button, Card, Sheet, Field, Skeleton, EmptyState,
    │                        ErrorState, Money, StatusPill, VerificationGate
    ├── theme/               tokens, typography, spacing, motion
    ├── lib/                 secure storage, money and phone format, analytics
    └── state/               session store, active-booking store
```

| Concern | Choice | Reasoning |
| --- | --- | --- |
| Server state | TanStack Query | Caching and retry matter more than usual on Nigerian networks |
| Client state | Zustand, two small stores | Session and active booking only |
| Forms | React Hook Form with Zod | Zod schemas mirror the backend service specs |
| Types | Generated from OpenAPI | The contract cannot silently drift from the app |
| Google sign-in | Native sheet, ID token to the API | Needs a dev build and three OAuth client ids |
| Animation | Reanimated and Haptics | Transitions, sheet physics, status changes |
| Lists | FlashList | Booking history on low-end Android |
| Sheets | gorhom/bottom-sheet | Request flow, verification prompts, tracking |
| Maps | react-native-maps | Dispatch tracking, address pin-drop. Dev build |
| Secrets | expo-secure-store | Refresh tokens never touch AsyncStorage |
| Testing | Jest, Testing Library, MSW | Hooks, state machine, gating, critical flows |

Native module versions come from the Expo SDK manifest via `npx expo install`, never
from npm latest. The SDK manifest and npm latest disagree for several packages.

### Verification handled once

Gating lives in a single `VerificationGate` wrapper rather than in each screen. The
API response is authoritative: if the server returns a verification code the client
did not predict, the gate renders from the server payload rather than its local
guess. That keeps a stale app honest.

### Network realism

Every mutating request carries a client-generated idempotency key, retries are safe
by construction, payloads stay small, and the app treats a timeout as unknown rather
than failed.

---

## 5. Django architecture

Nine domain apps under `backend/apps/`. The split follows lifecycle ownership, not
table count. Anything that would be a single module today lives inside the app that
owns its lifecycle rather than becoming its own app.

```
backend/apps/
├── common/         base models, money, phone, NG choices, pagination,
│                   error envelope, permission classes, idempotency
├── accounts/       User, SocialAccount, VerificationChallenge, Address,
│                   capability policy, device tokens
├── catalog/        ServiceCategory, Service, options, specs/ registry
├── providers/      profile, verification, offered services, areas, availability
├── bookings/       Quote, Booking, status events, Offer, matching engine
├── payments/       intents, transactions, gateway adapters, webhooks
├── wallets/        provider wallet, ledger, payout accounts, payouts
├── reviews/        ratings and review moderation
├── disputes/       dispute threads and resolution
└── notifications/  templates, email, SMS and push delivery, preferences
```

Matching lives inside `bookings` as `bookings/matching.py`, because an offer is a
stage of a booking's life and splitting it would add an import boundary with no
owner behind it. The capability policy lives in `accounts` because that is where the
facts it reads are stored.

### Conventions

- **Settings split** into `config/settings/{base,dev,prod,test}.py`, secrets from
  environment via `django-environ`, `TIME_ZONE = "Africa/Lagos"` with `USE_TZ = True`.
- **UUID primary keys** on every domain model, so identifiers are safe to expose in a
  public mobile API and enumeration reveals nothing about volume.
- **Money as integer kobo** in `BigIntegerField`. Exact by construction, and it
  matches the unit Paystack speaks at the boundary. Serializers expose both the
  integer and a formatted naira string.
- **Argon2 password hashing**, with Django's validators.
- **Business logic in service functions** under each app's `services.py`, not in views
  and not in `save()`. Views validate, authorize, call, and serialize.
- **State transitions only through** `bookings.state.transition()`, which validates the
  move, writes an append-only `BookingStatusEvent`, and emits notifications. No view
  assigns `booking.status` directly.
- **Append-only financial records.** Ledger entries and status events are never updated
  or deleted. Corrections are new compensating rows.
- **Endpoints are private by default.** `DEFAULT_PERMISSION_CLASSES` is
  `IsAuthenticated`, so a forgotten permission fails closed. Public routes declare
  `AllowAny` explicitly.
- **Tooling**: ruff for lint and format, mypy with django-stubs, pytest with
  pytest-django and factory-boy, coverage reported but not gated on a number.

---

## 6. Domain models

Field lists are the intended shape, not final migrations. Every model carries `id`
(UUID), `created_at` and `updated_at` from `apps.common.models.BaseModel` unless
noted as append-only.

### accounts

- **User**: `email` (unique, case-insensitive, USERNAME_FIELD), `password` (may be
  unusable), `phone` (E.164, unique when set, nullable), `first_name`, `last_name`,
  `email_verified_at`, `phone_verified_at`, `is_active`, `is_staff`, `last_active_at`
- **SocialAccount**: `user`, `provider` (GOOGLE), `provider_account_id`,
  `provider_email`, unique on (provider, provider_account_id)
- **VerificationChallenge**: `user`, `channel` (EMAIL / PHONE), `destination`
  (snapshotted), `purpose` (SIGNUP / LOGIN / EMAIL_CHANGE / PHONE_CHANGE /
  PASSWORD_RESET / SECURITY_CONFIRMATION), `code_hash`, `expires_at`, `consumed_at`,
  `attempt_count`, `resend_count`, `last_sent_at`, `request_ip`, `user_agent`
- **Address**: `user`, `label`, `street_address`, `landmark`, `area`, `lga`, `state`
  (36 plus FCT), `latitude`, `longitude`, `directions_note`, `is_default`
- **DeviceToken**: `user`, `expo_push_token`, `platform`, `app_version`, `last_seen_at`

### catalog

- **ServiceCategory**: `slug`, `name`, `description`, `icon_key`, `sort_order`, `is_active`
- **Service**: `category`, `slug`, `name`, `summary`, `spec_key`, `booking_modes`,
  `base_price_kobo`, `pricing_model`, `commission_rate`, `min_lead_time_minutes`,
  `cancellation_window_minutes`, `additional_requirements`, `is_active`
- **ServiceOption**: `service`, `key`, `label`, `kind`, `price_delta_kobo`, `sort_order`

### providers

- **ProviderProfile**: `user` (1:1), `display_name`, `bio`, `photo`, `business_name`,
  `provider_type`, `verification_status`, `rating_avg`, `rating_count`,
  `completed_jobs`, `acceptance_rate`, `is_accepting_jobs`
- **ProviderVerification**: one row per submission. `provider`, `status`,
  `submitted_at`, `reviewed_by`, `reviewed_at`, `rejection_reason`,
  `identity_check_status`, `identity_vendor`, `identity_reference`, `identity_method`,
  `masked_identifier` (last 4 only), `identity_checked_at`, guarantor fields
- **ProviderDocument**: `verification`, `kind`, `file` (private storage), `status`,
  `reviewer_note`
- **ProviderService**, **ProviderServiceArea**, **AvailabilityRule**, **AvailabilityException**

### bookings

- **Quote**: `service`, `customer`, `details`, `line_items`, `subtotal_kobo`,
  `service_fee_kobo`, `discount_kobo`, `total_kobo`, `spec_version`, `expires_at`
- **Booking**: `reference` (human, e.g. SY-8F3K2A), `customer`, `service`, `provider`,
  `quote`, `address`, `status`, `details`, `scheduled_for`, `preferred_provider`,
  `total_kobo`, `payment_method`, per-transition timestamps
- **BookingStatusEvent** (append-only): `booking`, `from_status`, `to_status`,
  `actor_type`, `actor_id`, `reason`, `metadata`
- **Offer**: `booking`, `provider`, `kind` (DIRECT / BROADCAST), `wave`, `sent_at`,
  `expires_at`, `responded_at`, `response`, `decline_reason`
- **Cancellation**: `booking`, `cancelled_by`, `reason_code`, `note`, `fee_kobo`

### payments and wallets

- **PaymentIntent**: `booking`, `customer`, `amount_kobo`, `method`, `gateway`,
  `gateway_reference`, `status`, `authorization_url`, `idempotency_key`
- **Transaction**, **WebhookEvent** (unique `event_id`), **SavedAuthorization**
- **ProviderWallet**: `provider` (1:1), `available_kobo`, `pending_kobo`
- **LedgerEntry** (append-only): `wallet`, `booking`, `type`, `amount_kobo` (signed),
  `balance_after_kobo`, `description`
- **PayoutAccount**, **Payout**

The ledger is why cash works. On a card booking Sync holds the money and releases the
provider's share on completion. On a cash booking the provider is paid directly, so
commission is owed the other way and lands as a negative ledger entry that nets
against future earnings. Without an append-only ledger, cash and card would need two
incompatible accounting paths.

### reviews and disputes

- **Review**: `booking` (1:1), `customer`, `provider`, `rating`, `comment`, `tags`,
  `is_visible`
- **Dispute**, **DisputeMessage**

---

## 7. API structure

Versioned at `/api/v1/` and namespaced by audience. Customer and provider need
different serializers, permissions and shapes of the same booking, so separating them
beats one polymorphic endpoint set full of role branching.

Every route carries a trailing slash, matching Django's `APPEND_SLASH` default. The
paths below are written without one for readability; the implemented routes have it.

### Authentication

```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/google              Google ID token, creates or links
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/auth/me
```

### Verification

```
GET    /api/v1/auth/verification        the checklist the app renders
POST   /api/v1/auth/email/verification/request
POST   /api/v1/auth/email/verification/confirm
PUT    /api/v1/auth/phone               set or change, opens a challenge
POST   /api/v1/auth/phone/verification/request
POST   /api/v1/auth/phone/verification/confirm
```

### Credentials and linked methods

```
POST   /api/v1/auth/password/reset/request
POST   /api/v1/auth/password/reset/confirm
POST   /api/v1/auth/password/set        for accounts created through Google
POST   /api/v1/auth/password/change
GET    /api/v1/auth/identities
POST   /api/v1/auth/identities/google
DELETE /api/v1/auth/identities/{id}     refuses to remove the last method
```

### Catalog, open to unverified users

```
GET    /api/v1/catalog/categories
GET    /api/v1/catalog/services/{slug}  includes the spec's field schema
GET    /api/v1/catalog/services/{slug}/providers
```

### Customer

```
GET    /api/v1/customer/addresses
POST   /api/v1/customer/quotes          open, so price is visible before verifying
POST   /api/v1/customer/bookings        gated, idempotent
GET    /api/v1/customer/bookings        cursor paginated
POST   /api/v1/customer/bookings/{id}/cancel
POST   /api/v1/customer/bookings/{id}/confirm-completion
POST   /api/v1/customer/bookings/{id}/review     gated
POST   /api/v1/customer/payments/intents         gated, idempotent
```

### Provider

```
GET    /api/v1/provider/onboarding      server-computed checklist
POST   /api/v1/provider/verification
POST   /api/v1/provider/verification/documents
PUT    /api/v1/provider/services
PUT    /api/v1/provider/availability
GET    /api/v1/provider/offers
POST   /api/v1/provider/offers/{id}/accept       gated, contended, locked
POST   /api/v1/provider/bookings/{id}/status
GET    /api/v1/provider/wallet
POST   /api/v1/provider/payouts                  gated
```

### Machine to machine

```
POST   /api/v1/webhooks/paystack        signature verified, idempotent by event id
```

Admin operations run on customised Django admin for Phase 1. Provider verification
review, dispute resolution, service management and manual assignment are admin views
over the same service functions the API calls.

### Cross-cutting conventions

- **Auth**: JWT via SimpleJWT, short access token, rotating refresh in secure storage.
- **Errors**: one envelope, `{"error": {"code", "message", "details"}}`, with stable
  machine codes. Never a bare string. Implemented in `apps/common/exceptions.py`.
- **Enumeration guards**: registration with an existing email, password reset for an
  unknown address, and login failures return the same shape regardless of whether the
  account exists.
- **Idempotency**: an `Idempotency-Key` header on every POST that creates a booking or
  moves money, backed by a short-lived record of the first response.
- **Pagination**: cursor for anything time-ordered, page number for catalog.
- **Schema**: drf-spectacular generates OpenAPI, which generates the mobile types in
  CI. Drift becomes a failing build.
- **Versioning**: an `X-Client-Version` header so a minimum supported version can be
  enforced later.

---

## 8. Navigation structure

There is deliberately no verification gate between `(auth)` and `(customer)`. A newly
registered, entirely unverified user lands on the home tab like anyone else.

```
app/
├── _layout.tsx              fonts, query client, session gate
├── (auth)/
│   ├── welcome.tsx          continue with Google, or email
│   ├── register.tsx
│   ├── login.tsx
│   ├── forgot-password.tsx
│   ├── reset-password.tsx
│   ├── verify-email.tsx
│   ├── verify-phone.tsx
│   └── profile-setup.tsx    skippable, not a wall
├── (customer)/
│   ├── (tabs)/
│   │   ├── index.tsx        home, plus the verification checklist while incomplete
│   │   ├── bookings.tsx
│   │   └── account.tsx      addresses, payment, linked sign-in methods
│   ├── verification.tsx
│   ├── category/[slug].tsx
│   ├── service/[slug]/
│   │   ├── details.tsx      spec-driven step
│   │   ├── schedule.tsx
│   │   ├── address.tsx      saved, or map plus landmark
│   │   ├── provider.tsx     optional: pick a specific provider
│   │   └── review.tsx       quote breakdown, then the gate fires here
│   ├── booking/[id]/
│   │   ├── index.tsx
│   │   ├── track.tsx        map, dispatch and errands only
│   │   └── rate.tsx
│   └── provider/[id].tsx
└── (provider)/
    ├── (tabs)/
    │   ├── jobs.tsx
    │   ├── earnings.tsx
    │   └── account.tsx
    ├── onboarding/
    └── job/[id].tsx
```

Three details carry weight. The verification gate is a sheet raised over the current
screen, not a route push, so a customer who verifies mid-booking returns to exactly
where they were with their draft intact. An incoming offer arrives as a modal with a
visible countdown, because an offer that requires navigation to find is an offer that
expires. And an active booking is pinned to the top of the customer home tab.

The gate fires on the quote review screen, after the customer has seen the real price,
not on entry to the request flow. Asking someone to verify a phone number before they
know what a service costs is how you lose them.

---

## 9. Design system

A small token set, strictly applied. The premium feeling comes from restraint and
consistency, not decoration.

**Color.** One accent, reserved for primary actions and active state. Nigerian
fintech and telco have saturated green, yellow, orange and purple, so a deep,
low-saturation ink-teal reads as calm and unclaimed. Neutrals carry the interface:
a near-black ink, three grey steps, one hairline, one sunken surface. Semantic colors
are separate from the accent and used only for meaning. Category identity is an icon
and an illustration, not six brand colors, because six competing hues is how this
stops feeling like one product.

**Typography.** One variable family, hierarchy from weight, size and tracking. A
seven-step scale: 12, 14, 16, 18, 22, 28, 34. Tabular figures wherever money or counts
appear. Naira formatted through one `Money` component, never by hand at a call site.

**Space, shape, motion.** 4pt base scale. Radii of 12, 16 and 20 applied by role
(control, card, sheet). Motion between 150 and 250ms, spring physics for sheets, no
overshoot bounce, all respecting reduce-motion. Haptics on state-changing
confirmations only.

**States as first-class components.** Every list and detail screen ships a skeleton
that matches the real layout, an empty state with an action, an error state that says
what failed and offers a retry, and an offline state that distinguishes no connection
from request failed. The verification gate is the fifth member of that family.

**Accessibility.** Minimum 44pt touch targets, labels on every control, WCAG AA
contrast, type that scales with the OS setting, and status never communicated by color
alone. Verification code fields accept paste and one-time-code autofill.

Phase 1 ships light only, with tokens structured so dark mode is a palette swap.

---

## 10. Milestones

| M | Milestone | Ends with |
| --- | --- | --- |
| M0 | Foundation: monorepo, settings split, Postgres, Redis, DRF, health endpoint, Expo scaffold, API client, CI | Both apps boot, CI green, device reaches the API |
| M1 | Identity: User, registration and login, Google and linking, JWT, verification challenges, capability policy, rate limiting, addresses | A user registers, explores unverified, and is blocked usefully at the first gated action |
| M2 | Catalog and specs: categories, services, spec registry, pricing, home and browse | Six categories browsable with real content and prices, without an account |
| M3 | Booking core: Quote, Booking, state machine, status events, request flow, Cleaning only | A cleaning is requested, priced, and tracked through every state |
| M4 | Provider side: onboarding, documents, identity check, admin review, availability, matching, offers | A verified provider receives an offer, accepts, and completes the job |
| M5 | Money: Paystack charge and webhook, escrow release, commission, ledger, payouts, cash | Real money in, correct split, real payout out |
| M6 | Remaining verticals, each as a spec plus a details step | All six live, core booking code unchanged since M3 |
| M7 | Trust and operations: reviews, disputes, notifications, admin hardening, manual assignment | Operations can run the marketplace without a developer |
| M8 | Launch readiness: performance, error tracking, analytics, security review, store submission | Builds submitted to both stores |

Cleaning is deliberately the first vertical rather than dispatch. It is scheduled
rather than on-demand, needs no maps and no live location, and still exercises
quoting, matching, the full state machine, payment and rating. Dispatch adds
real-time tracking, which is a large and separable problem.

If M6 requires changes to core booking code, the abstraction is wrong and we stop and
fix it. That is the point of doing M3 on a single vertical.

---

## 11. Risks and open decisions

### Open

0. **Production SMS and email providers.** Both verification flows are built and
   work end to end, but neither has a real provider configured: `SMS_BACKEND`
   defaults to the console provider and `EMAIL_BACKEND` to Django's console
   backend, so both print rather than send. Nobody on a real device can receive a
   code until providers are chosen, credentialed and set. Termii is the documented
   intention for SMS. This is the last thing standing between the current build
   and a customer booking, or a provider accepting, unaided.

   `ACCEPT_JOB` is now settled at `PHONE_VERIFIED` plus `EMAIL_VERIFIED`.
   `REQUEST_PAYOUT` (M5) is still an empty row in the same table.

1. **Local infrastructure.** Docker Compose is the chosen approach and the file is in
   the repository, but Docker Desktop must be installed on each development machine.
2. **Escrow posture.** Holding customer funds between payment and completion is what
   makes the marketplace trustworthy, and it means Sync holds money it does not own.
   This has CBN and licensing implications at scale. The engineering design is the
   same either way. Worth legal advice before M5.
3. **Commission model.** Flat across categories or per-category. Dispatch and laundry
   have thin margins where a flat 20 percent does not work. Per-category, configurable
   on the `Service` row, is the recommendation and is already in the model.
4. **Which requirements gate which actions.** The policy table in section 3 trades
   conversion against abuse. The specific question is whether a first booking should
   require phone verification or only email. The recommendation is both for dispatch
   and errands, email only for the scheduled categories.

### Managed

| Risk | Why it matters here | Mitigation |
| --- | --- | --- |
| OAuth account takeover | Auto-linking on an unverified email hands over the account | ID token verified server-side, `email_verified` is a hard gate |
| Email deliverability | Verification and password reset both run on it | Reputable provider with SPF, DKIM and DMARC from M1 |
| Verification drop-off | Progressive verification moves friction to first booking | Gate fires after price is shown, flow is inline, instrumented from M1 |
| Cold-start supply | Matching fails silently with four providers in a city | Admin manual assignment from day one, honest waiting states |
| Cash breaks escrow | Cash inverts the money flow, commission becomes a debt | The append-only ledger handles both directions |
| Address quality | Nigerian addresses are often wrong, geocoding unreliable | Landmark is prominent and near-required, pin-drop offered, call button |
| Network flakiness | A dropped response produces duplicate bookings | Idempotency keys, backoff, small payloads, honest offline states |
| SMS cost and abuse | Phone verification can be weaponised against a stranger | Per-destination limits, resend cooldown, attempt cap |
| Offer race conditions | Several providers can accept within milliseconds | Accept runs in a transaction with `select_for_update` |
| Home entry safety | A stranger in a customer's home. One incident is existential | Approval gates job access, identity shown before arrival, disputes |
| Dev build requirement | Google sign-in, maps and push all break Expo Go, now at M1 | EAS dev builds from M0, OAuth client ids before M1 |
| Multi-vertical dilution | Six categories at once risks six mediocre experiences | M3 proves the core on one vertical first |

### Deliberately not building yet

PostGIS and radius search (coordinates are stored, filtering is by area), a separate
admin SPA, websockets (short-interval polling suffices until M6), social providers
beyond Google, two-factor authentication (the challenge model already supports it via
`SECURITY_CONFIRMATION`), microservices, GraphQL, a shared design-token package, and
any recommendation or surge-pricing engine. Each has a clear trigger point, and none
of them is today.
