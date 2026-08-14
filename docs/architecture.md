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
costs conversion at the moment of commitment. M4 and M5 each added a capability to
the same table without touching the booking domain.

**Deletion.** `customer`, `provider` and `service` are all `PROTECT`. A booking is
a record of something that happened between two people and must outlive a profile
tidy-up, so an account with bookings is deactivated rather than deleted.

**A booking carries the price it was agreed at.** `total_kobo` is snapshotted at
creation from the named provider's price or the catalog price, and never rewritten.
Added in M5 because a settlement needs an amount that a later price change cannot
reach; the reasoning is in the money section below.

Deferred from the booking domain, with the milestone that owns each: the `Quote`
model and per-vertical pricing functions, availability windows, the `Cancellation`
model with fees, `DISPUTED` (M7), and `DRAFT` / `QUOTED` / `PENDING_PAYMENT`, which
are defined above but have no meaning until the milestones that produce them exist.
M5 gave a booking a price without giving it a quote: one number agreed at creation
is what settlement needs, and a line-item breakdown is what a quote adds.

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

### Money, as implemented in M5

M5 is the financial domain, not the payment integration. No gateway is involved:
nothing charges a customer and nothing moves money to a bank. What exists is the
record of what was earned, whose it is, and what has been asked for, built so that
a transfer adapter can be added later without any of it being rewritten.

**Three conflicts with earlier revisions of this document were resolved here, and
the resolutions are the current design.**

| This document used to say | What was built, and why |
| --- | --- |
| A `wallets/` app beside `payments/` | One `payments/` app. Splitting a settlement from the payout that draws on it puts an import boundary through the middle of one balance calculation, with no separate owner behind it. The gateway adapters land inside `payments/gateways/` when they arrive |
| `ProviderWallet.available_kobo`, a stored balance | No balance column exists. It is derived on every read from the settlements and payouts themselves, which is the same principle the append-only ledger was reaching for. A stored balance is a number that can be wrong for a month before anybody notices |
| `LedgerEntry`, signed amounts, `balance_after_kobo` | Not built. The ledger's job is to reconcile money flowing in two directions, which is a cash-versus-card problem, and cash payment does not exist yet. Building the general machine before the case that needs it would be guessing at the shape of the case |

**Money is an integer number of kobo, everywhere, with no exception.** No float
appears anywhere in `apps/payments`, and the one calculation the domain performs is
a pure function over integers. A commission rate is basis points, an integer
hundredth of a percent, precisely so that a percentage never invites a float in.

#### Settlement

A completed booking earns exactly one `BookingSettlement`, written in the same
transaction as the completion itself. Either both happen or neither does, so there
is no window in which a booking is finished but has earned nobody anything.

```
booking reaches COMPLETED -> settlement written, status PAYABLE
```

One status, deliberately. A settlement is only ever created for work that is
already finished and confirmed, so it has no earlier state to sit in, and it is
immutable, so it has no later one to move to. The field exists rather than being
inferred because a dispute resolved in the customer's favour will need a
compensating record with a state of its own, and adding it then must not mean
teaching old rows what state they were always in.

**Everything monetary on the row is a copy.** The gross comes from the booking's
own agreed total, not from the Service. The rate applied is written onto the row,
not looked up later. Verified live: raising the catalog price tenfold, setting a
provider override to one kobo, and changing the commission rate all leave an
existing settlement untouched, and the next booking picks up the new rate while the
old one keeps its own.

**The invariant is a database check constraint**, not an application assertion:

```sql
provider_amount_kobo = gross_amount_kobo - commission_amount_kobo
```

alongside non-negativity on all three amounts and a constraint that commission can
never exceed the gross. The provider's share is derived by subtraction rather than
by a second multiplication, which is what makes the equality exact rather than
approximately true.

**Rounding is floor division, so the fraction of a kobo goes to the provider.** A
rounding rule has to be chosen deliberately, and the one that never rounds in our
own favour is the one that can be defended to a provider reading their statement.

#### The booking price

Settlement needs an amount, and until M5 a booking carried none. `Booking.total_kobo`
is now snapshotted at creation, for the same reason the address is: a catalog price
and a provider's override are both mutable rows, and settling finished work against
today's price would let a price change reach backwards into money already earned.

A customer who names a provider is quoted that provider's price, override included.
A customer who does not is quoted the catalog price, and whoever wins the broadcast
takes the job at the price the customer already agreed to. Repricing after
acceptance would mean the figure on the review screen was never binding, which is a
worse promise than a provider occasionally earning their catalog rate.

#### Commission

**One flat rate, in settings, at 2000 basis points.** Section 11 records
per-category commission as an open question, and answering it by adding a rate
column to `Service` would settle a pricing decision nobody has taken. Moving the
setting affects the next completed booking and can never reach a past one, because
the rate each settlement used is on that settlement.

#### Balance

There is no balance to maintain, so there is nothing to drift:

```
available = sum(settlement.provider_amount)
          - sum(payout.amount where REQUESTED or PROCESSING)
          - sum(payout.amount where PAID)
```

Money in a requested or processing payout is subtracted although it has not left,
because counting it as available is exactly how the same earnings get claimed twice.
A failed or cancelled payout subtracts nothing, so the money returns to the balance
by arithmetic rather than by anyone remembering to credit it back.

Payouts are not allocated against particular settlements. A payout is a claim on a
balance, and the balance is a sum over immutable rows on both sides, so an
allocation table would be a third thing to keep in step with two sources of truth
that already agree by construction.

#### Payout lifecycle

```
REQUESTED -> PROCESSING -> PAID
          -> CANCELLED              by the provider, while still REQUESTED
          -> FAILED                 either state, by the trusted path
```

Actor-aware, like every other lifecycle here, and this time the actors are the whole
point. Only `SYSTEM` and `ADMIN` appear on the edges ending in `PROCESSING` or
`PAID`; a provider holds exactly one move, cancelling their own request, because
cancelling releases money back to them and takes nothing from anybody. No endpoint
in the API accepts a status, and no code path hands a provider a `SYSTEM` or `ADMIN`
actor type. The trusted transitions live in the Django admin as named actions
calling the same service function a transfer adapter will call.

A failed payout is terminal rather than returning to `REQUESTED`. The money comes
back to the balance either way, and a fresh request leaves a clean record of two
attempts instead of one row that quietly changed its mind.

#### Concurrency

Two guarantees, neither trusted alone. Requesting a payout locks the provider's own
row with `select_for_update`, so simultaneous requests serialise and the second
reads a balance that already accounts for the first. Behind that, a partial unique
index permits at most one payout per provider in `REQUESTED` or `PROCESSING`, so
even if the reasoning above were wrong only one could commit. Settlement is the
same shape: the booking row is locked, and a one-to-one constraint is the final
word.

Verified against a real database with real threads: two providers racing for one
balance produce one payout and a non-negative balance, four at once produce one
payout, and three simultaneous completions of one booking produce one settlement.

#### Idempotency

The mobile client already sends an `Idempotency-Key` header on anything that moves
money. M5 is where the server half of that lands, and it is a field with a partial
unique index rather than a new mechanism: `PayoutRequest.idempotency_key`, unique
per provider when non-blank. A repeat carrying a key that already succeeded returns
the payout that request created. Blank is the absence of a key rather than a key
everybody shares, which is why the uniqueness is partial.

Repeated booking completion needs no key. The lifecycle refuses a second move to
`COMPLETED`, and underneath that the one-to-one constraint refuses a second
settlement.

#### Payout destination

The minimum a transfer provider will need, and nothing beyond it. **The account
number is not stored.** It arrives, it is used to show the provider what they typed,
and what persists is an Argon2 hash, the last four digits, and an empty slot for the
recipient token a transfer provider will issue. That is the same posture identity
verification already takes with NIN and BVN, for the same reason.

This is affordable because the adapter will be called at the moment the number is
supplied, and from then on the token moves the money. Nothing stores a card number,
a CVV, a bank password, or any provider secret, and none of those are needed to pay
a Nigerian provider.

#### Still deferred after M5

Charging the customer at all, which was the largest single gap and is what M6A
closes. Transfer execution and payout webhooks, refunds and chargebacks, cash
bookings and the ledger that inverts commission for them, cancellation fees,
disputes reversing a settlement, background expiry of stale payouts, per-category
commission, and accounting exports.

### External integrations, as implemented in M6A

M6A makes the outside world real. Five boundaries, all the same shape: an
interface the domain depends on, one module per vendor that knows what that
vendor's API looks like, a deterministic fake, and a setting that chooses. No
domain module imports a vendor, mentions one, or knows the shape of its payloads.

| Concern | Interface | Production adapter | Local and test default |
| --- | --- | --- | --- |
| Taking payment | `payments/gateways/base.PaymentGateway` | `gateways/paystack.py` | `gateways/fake.py` |
| Confirming a bank account | `payments/banks/base.BankAccountResolver` | `banks/paystack.py` | `banks/fake.py` |
| SMS | `accounts/sms/base.SMSProvider` | `sms/termii.py` | `sms/console.py`, `sms/locmem.py` |
| Email | Django's `EMAIL_BACKEND` | `accounts/email/resend.py` | Django's console backend |
| Webhooks | `payments/webhooks.WebhookEvent` | one route per provider | signed locally by the fake |

**The suite needs no external account.** Test settings pin every integration to a
fake and blank the real keys, so a test that would only pass by reaching a live
provider fails instead. Importing Django opens no connection: every adapter is
built on use, never at import.

**Credentials come only from the environment**, are listed in `.env.example`, and
have no defaults. A production adapter constructed without its key raises
immediately rather than at the first payment, so a misconfigured deployment is
obvious before it can swallow anything.

**Why Resend for email.** Section 2 left this open between Resend and AWS SES.
Resend needs an API key and a verified domain; SES needs an AWS account, an IAM
user, a sandbox exit request a human reviews, and a region decision. For a
product that has not launched the setup cost is the whole difference, and SES's
advantage is per-message price at a volume nobody here has yet. Moving to SES is
a different `EMAIL_BACKEND` and no other change, which is what the boundary is
for. Termii for SMS was already the documented intention and is unchanged.

#### Payment lifecycle

`PaymentIntent`, the name section 6 already gave this. An attempt to collect,
which is not the same thing as a payment.

```
INITIALIZED -> SUCCESSFUL     the provider says the money moved
            -> FAILED         the provider says it did not
```

**Nothing a client sends can make one successful.** There are exactly two writers
of that status: verification, which fetches the provider's own account of the
transaction, and a signature-checked webhook. Both run the same function, and it
refuses unless the amount and currency match what we recorded. A request body
containing a success claim is not read at all, and there is no PATCH or PUT on a
payment by any route.

**The amount is the booking's snapshotted total.** Nothing in the payment path
reads a Service or a ProviderService, so a price change between booking and
payment cannot alter what a customer is charged.

**A booking is paid for once**, enforced by a partial unique index permitting at
most one `SUCCESSFUL` intent per booking. A failed attempt followed by a
successful one is two intents and one payment. Two successful ones is impossible.

**Terminal is terminal.** A late webhook about a payment that already succeeded
changes nothing, and one about a payment that already failed cannot resurrect it:
only a fresh attempt can. That is what makes out-of-order delivery safe.

A booking is payable in every status except `CANCELLED` and `EXPIRED`, `COMPLETED`
included. Paying after the work is done is an ordinary sequence, not an error.

#### Payment and settlement

**M5's rule changes here, deliberately and visibly.** M5 wrote a settlement when a
booking reached `COMPLETED`, because no payment existed to wait for. A settlement
now needs both:

```
booking COMPLETED  and  a SUCCESSFUL payment   ->  settlement
```

Either can happen first, and whichever happens second writes it. A customer may
pay up front and confirm days later, or pay after the work is done; both are
ordinary and both are tested. A completed booking with no successful payment
earns its provider nothing, which is the point: provider earnings a customer
never funded would be a debt the marketplace has no way to cover.

`create_settlement` is the strict form and says why it refused, with
`SETTLEMENT_AWAITING_PAYMENT` distinguishing "not paid yet" from "not finished
yet". `settle_if_ready` is the forgiving form both hooks call, since arriving
second is a normal state rather than an error. The financial invariant, the
immutability and the one-settlement-per-booking constraint are all untouched.

#### Webhooks

Not a framework. One model and one rule: an event id is seen at most once,
enforced by a unique index on `(gateway, event_id)`. That is the whole of what
payment webhooks need now and what payout webhooks will need later.

**The signature is the authentication**, checked over the exact bytes received
before the body is parsed and before anything is written. Re-serialising parsed
JSON changes whitespace and key order and would never match, which is why the
view reads `request.body`. A body that fails is refused with a bare "Rejected."
and is not recorded: an attacker probing the endpoint learns nothing.

**The payload is not stored.** A charge payload carries the customer's email
address and their card's last four digits, and keeping a copy of every one of
those buys very little. What is kept is the handful of fields reconciliation
reads, plus a SHA-256 digest of the raw body so a disputed event can still be
matched against the provider's own record.

**Everything after a valid signature answers 200**, including an event about a
reference we never issued and one that arrived too late to matter. A provider
that receives anything else retries, and retrying will not change either.

Paystack puts no event id on the envelope, so the adapter builds one from the
event type and the transaction it concerns. Redelivery produces the same string;
two different events about one transaction stay distinct.

#### Bank account verification

Ten digits somebody typed is not an account. A provider who mistypes one would
otherwise have money sent into a stranger's account with nothing having looked
wrong, and the only check that catches it is asking the bank what name it holds.

A destination is `UNVERIFIED` until a resolver confirms it, and **a payout cannot
use an unverified destination**. The bank's answer is stored beside what the
provider typed rather than replacing it, so both can be shown and a mismatch is
visible. Changing either the account number or the bank discards the previous
confirmation, because a verification is a statement about one number at one bank
and says nothing about a different pair.

The account number is still not stored. It is supplied again to verify, which is
also how we check it is the number on file: a number that does not match the
stored hash is not this destination's account.

**`REQUEST_PAYOUT`'s capability requirements are unchanged.** Having somewhere to
be paid is a fact about the payout rather than about the account, so it is domain
validation with its own error code rather than a fourth row in the policy table.

#### Idempotency

The existing mechanism, extended to one more endpoint: the `Idempotency-Key`
header the mobile client already sends, stored as a field with a partial unique
index. A retried payment initialization returns the intent the first attempt
created and does not ask the provider to collect a second time.

Webhooks deduplicate on the provider's event id instead, because a provider does
not send our header. Repeated booking completion still needs neither, since the
lifecycle refuses a second `COMPLETED` and the one-to-one constraint refuses a
second settlement.

#### Checkout, on the mobile side

Payment happens on the provider's own hosted page, opened in the system browser
with `expo-linking`, which the app already depends on. Card details never touch
the app, so no build of it is in scope for PCI and it holds no provider
credential of any kind. It also needs no native module, so the project stays on
Expo SDK 54 and keeps working in Expo Go.

Returning from the browser proves nothing: a customer who closed the page and one
who paid look identical from the app's side. So the app asks the server to check,
and the server asks the provider.

#### Deferred from M6A

Background workers and queues, and therefore anything periodic: no reconciliation
sweep, no expiry of stale intents or offers. Payout execution and its webhooks,
which need Paystack Transfers and a funded balance. Refunds, chargebacks and the
`Transaction` model that becomes meaningful alongside them. Saved cards, and the
`SavedAuthorization` model with them. Escrow as a distinct held balance.

### Running unattended, as implemented in M6B

Everything above works while somebody is holding a phone. M6B is what makes it
work when nobody is. Five things happened on request until now and simply did not
happen otherwise: an offer's window passing, a payment nobody came back to
confirm, a transfer we submitted and never heard about, a challenge nobody used,
and any inconsistency between the three.

#### The job architecture

**Celery over the Redis that is already here**, which is what section 2 has
specified since M0. Importing Django starts nothing: a worker and a scheduler are
separate processes, and `manage.py` behaves exactly as it did.

```
worker:    celery -A config worker
scheduler: celery -A config beat
```

Tasks live in each app's `tasks.py`, beside the domain they act on. Test settings
run them eagerly, in the calling process, so **the suite needs no worker and no
broker**: a test calls a task like a function and sees its effect immediately.

`kombu`, Celery's transport library, declares `redis<6.5` while M0 had pinned the
redis client at 8.1.0. It connects fine on 8.1.0 and was verified doing so, but
that is untested-there rather than supported, and this project already took the
other side of exactly that question when it chose Django 5.2 over 6.1. The pin
moved to 6.4.0, which every maintainer declares and which nothing here needs a
newer feature than.

#### The contract every task follows

Fetch current state from the database. Lock the contested row. Re-check that the
work is still needed. Change it in one transaction. Be safe run twice, and safe
if the process dies at any point, including between an external call and
recording its result. Most repeat executions end at the third step having done
nothing, which is exactly right.

#### Three retry classes

The classification is a statement about money rather than about code.

| Class | Meaning | Tasks |
| --- | --- | --- |
| **Safe to retry** | Nothing outside changes, or the external call is a read | Offer expiry, challenge retirement, the consistency sweep, both reconciliations |
| **Requires reconciliation** | An external write whose result we may not have seen | Payout submission |
| **Never retry** | Repetition moves money twice and cannot be reconciled | Nothing, deliberately |

The third row is empty by design rather than by luck: the one operation that
would belong in it was made reconcilable so that it could sit in the second.

Safe tasks retry five times with jittered backoff from ten seconds to ten
minutes, then stop. A task that has failed five times will not succeed on the
sixth, and an unbounded retry fills a queue with work nobody will look at.

#### Payout execution, and the crash window

This is the one place the system sends money out, and the one place a request we
made and an answer we did not receive is a question about real naira.

**The window, stated plainly.** We call the provider. They receive it, start a
transfer, and begin their reply. The connection drops, or the process is killed.
Money has moved and we have no record of it. From our side that is
indistinguishable from a request that never arrived.

The system does not try to tell them apart at the moment of failure. Instead:

1. **A reference is reserved before the call.** `transfer_reference` is generated
   and committed, with the payout moved to `PROCESSING`, in a transaction that
   finishes before the provider is contacted. The instant it commits, the payout
   means "this may have moved money".
2. **A payout carrying a reference is never resubmitted.** Not by a retry, not by
   an operator, not by reconciliation. `execute_payout` refuses outright, and
   that refusal is the guarantee, independent of anything a vendor promises.
3. **Reconciliation asks, using our reference.** Because it was ours and was
   written first, the question always has somewhere to be asked. This is why the
   transfer interface requires `fetch(reference)`, and why a provider that cannot
   answer by our reference cannot be used here.

Paystack also treats a transfer reference as idempotent, so a resubmission would
return the original. That is a second line of defence and deliberately not the
first: relying on a vendor's idempotency for the one operation that must never
happen twice would be trusting a promise we cannot check.

**What each state means**, which is the vocabulary an operator needs:

| Payout state | What is true |
| --- | --- |
| `REQUESTED`, no reference | Definitely not sent |
| `PROCESSING`, reference, no gateway reference | Submitted, outcome unknown |
| `PROCESSING`, both references | Submitted, provider still working |
| `PAID` | Definitely successful |
| `FAILED` | Definitely failed, money available again |

A provider that refuses outright is different again: nothing was started, so the
payout is failed and its reserved reference cleared, because leaving one would
make it look forever like a payout that might have moved money.

**No new lifecycle state was invented.** `PROCESSING` plus the presence of a
reference carries the distinction, which keeps the guarded transition table
exactly as M5 defined it.

#### Payout reconciliation

For every payout in `PROCESSING` with a reference, ask the provider and apply the
answer through the same guarded lifecycle. Success pays it, failure fails it and
returns the money by arithmetic, still-processing leaves it, and **unknown leaves
it too**. That last one matters: a provider with no record of our reference today
may simply not have processed it yet, and releasing the money on that basis is
how it goes out twice. Terminal states are never revisited, so a late answer
cannot drag a `PAID` payout back.

#### Payment reconciliation

For payments left `INITIALIZED` longer than fifteen minutes, ask the gateway.
**Age is never evidence.** A payment pending for a week is one we have not
resolved, which is a different thing from one that failed, and an unknown
provider state never becomes `SUCCESSFUL`. A provider that cannot be reached
changes nothing at all. After seven days a payment stops being swept and is
recorded as needing a person, because asking an eighth time will not help and
sweeping it forever buries the ones that are still answerable.

#### Offer expiry

Offers past their window are closed through the existing guarded lifecycle, and a
booking with no answerable offer left moves `MATCHING -> EXPIRED`, which the
lifecycle has defined since M3 for a request nobody took. The history row records
which task did it. Nothing new was invented; the state simply became reachable
without somebody opening the app.

#### Anomalies, and what may be repaired

The consistency sweep reads our own rows and classifies what it finds. **Only one
kind is repaired automatically**: a booking that is completed and paid with no
settlement, where the invariant and the intended outcome are both unambiguous and
the code to produce it already exists.

Everything else is recorded in `FinancialAnomaly` for a person. A settlement with
no payment behind it is not deleted, because that would take a provider's
earnings away on the say-so of a sweep. A settlement whose amount disagrees with
its booking is not rewritten, because that is exactly what immutability forbids
and because the disagreement is the only evidence of whatever caused it. Open
anomalies deduplicate per subject, so an hourly sweep against an unfixed problem
produces one row with a count rather than one row an hour.

#### Webhooks stayed synchronous

M6A's webhook handler was reviewed and left alone. It verifies a signature,
writes a deduplication row, locks one payment and applies one answer: a handful
of indexed queries with no external call, which is already fast and already
idempotent. Handing that to a queue would add a delivery guarantee to something
that has one, and would introduce a window where we have acknowledged an event we
have not yet applied. Complexity for its own sake was declined.

#### Automatic payouts were not built

A provider still asks. What M6B adds is the execution of what they asked for,
released by an operator action in the admin that queues the same task any other
caller would use. Nothing pays anybody because earnings became available.
Removing the operator gate later is one call site, and is a business decision
rather than an engineering one.

#### Balance under all of this

Unchanged from M5, which is the point. There is still no stored balance:
available is summed from settlements minus live reservations and outflows on
every read. Execution reserves nothing new, because `PROCESSING` already
reserved. What execution adds is a recheck: the amount is recalculated from the
immutable records before the transfer is submitted, so a payout requested when
the money was there does not go out once it is not. Verified with real threads
that two workers sending one payout submit one transfer, and that requesting
while another payout executes cannot drive the balance negative.

#### Scheduling

| Task | Interval | Why |
| --- | --- | --- |
| Offer expiry | 60s | Offers run on a fifteen minute window; a minute of lag costs nobody anything |
| Payment reconciliation | 5m | Talks to Paystack. Far more often than a slow bank transfer needs |
| Payout reconciliation | 5m | The task that closes the crash window |
| Challenge retirement | 1h | Tidies rows that are already unusable |
| Consistency sweep | 1h | Reads our own rows; the slowest query of the five |

Every interval and every batch size is an environment variable. Batches are
bounded at two hundred rows, so a bad day cannot produce a task that holds locks
for minutes, and whatever is left is picked up on the next tick. Several workers
running the same schedule is safe and is tested.

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
| Payouts | Paystack Transfers | `payments/transfers/base.py`, not built |
| Transactional email | Resend | Django's `EMAIL_BACKEND`, `accounts/email/` |
| SMS | Termii | `accounts/sms/base.py` |
| Identity verification | Prembly, Youverify or VerifyMe | `providers/identity/base.py`, not built |
| Bank account resolution | Paystack | `payments/banks/base.py` |
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

### What registration asks for

Email, password and **a phone number, required**. Booking needs a verified phone,
and an account with no number on file cannot begin that: it is a form away rather
than a code away. Support also has no way to reach the person behind such an
account, which matters from the moment one exists rather than from the first
booking.

**Requiring the number is not requiring it verified.** The account is created with
`phone_verified_at` unset, and the booking gate still demands a code, which is what
stops signup being a way to claim somebody else's number.

**The column stays nullable, and no migration was needed**, for three independent
reasons. Google sign-in creates an account from an ID token carrying no phone
number, so the model has to be able to hold one without. `phone` is unique, and in
PostgreSQL nulls do not collide under a unique index while a placeholder would, so
NOT NULL plus unique would mean every account needs a real distinct number
including ones created by `createsuperuser`. And requiring a number is a rule about
one form rather than about the shape of a user, so it belongs in the registration
serializer, which is where it is enforced.

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
# apps/accounts/policy.py, as implemented

CAPABILITY_REQUIREMENTS = {
    Capability.CREATE_BOOKING:  [PHONE_VERIFIED],
    Capability.ACCEPT_JOB:      [PHONE_VERIFIED, EMAIL_VERIFIED],
    Capability.REQUEST_PAYOUT:  [PHONE_VERIFIED, EMAIL_VERIFIED],
}
```

`MAKE_PAYMENT` and `LEAVE_REVIEW` are rows for the milestones that create them.

**`PROVIDER_APPROVED` is deliberately not a requirement in this table**, although an
earlier revision of this document listed it on both `ACCEPT_JOB` and
`REQUEST_PAYOUT`. Approval is enforced structurally instead, and more strictly than
a policy row would manage: only an approved provider is ever sent an offer, so an
unapproved one cannot reach a job at all, and cannot then reach the settlement that
a payout would draw on. Adding the row would change nothing except the wording of
the refusal, and it would change it for the worse, since an unapproved provider
asking for a payout would be told about approval when the true answer is that they
have not earned anything.

`PAYOUT_ACCOUNT_VERIFIED` is likewise not a requirement. Having somewhere to be paid
is a fact about the payout, not about the account, so it is validated by the payout
domain and refused with `INVALID_PAYOUT_DESTINATION`. Verifying that an account
belongs to the person claiming it needs a name enquiry at a bank, which is a
transfer provider's job and arrives with the adapter.

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

**The app is pinned to Expo SDK 54, not the newest SDK.** Expo Go on the app stores
supports only the current SDK, so a project on a newer one cannot be opened by an
Expo Go that has not updated. The development device available for testing is on
SDK 54 and cannot update, so the project matches it rather than the device matching
the project. The downgrade from 57 cost no application code: the suite passed
unchanged, because nothing here touches an API that moved between those releases.

This is a testing convenience with an expiry date. Google sign-in, maps and push all
require a development build rather than Expo Go, and the first of those forces the
issue. When a dev build exists the SDK pin is free to move again, and moving it is
the preferred direction: SDK 54 leaves the project on React Native 0.81 and React
19.1 while the ecosystem moves on.

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

Eight domain apps under `backend/apps/`. The split follows lifecycle ownership, not
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
├── payments/       settlements, earnings, payouts, payout destinations,
│                   payment intents, gateway adapters, bank resolution,
│                   webhook events
├── reviews/        ratings and review moderation
├── disputes/       dispute threads and resolution
└── notifications/  templates, email, SMS and push delivery, preferences
```

Matching lives inside `bookings` as `bookings/dispatch.py`, because an offer is a
stage of a booking's life and splitting it would add an import boundary with no
owner behind it. The capability policy lives in `accounts` because that is where the
facts it reads are stored. `payments` owns the whole financial domain for the same
reason matching is not its own app: an earlier revision of this document split it
into `payments` and `wallets`, which would have put an import boundary through the
middle of a single balance calculation.

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
  unusable), `phone` (E.164, unique when set, nullable at the database level and
  required by the registration form), `first_name`, `last_name`,
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

### payments

Built in M5:

- **BookingSettlement**: `booking` (1:1), `provider`, `gross_amount_kobo`,
  `commission_amount_kobo`, `provider_amount_kobo`, `commission_rate_bps`,
  `currency`, `status`. Written once, never updated
- **PayoutRequest**: `provider`, `amount_kobo`, `currency`, `status`, `requested_at`,
  `processed_at`, `failure_reason`, `idempotency_key`
- **PayoutDestination**: `provider` (1:1), `bank_code`, `bank_name`, `account_name`,
  `account_number_last4`, `account_number_hash`, `provider_reference`, `is_active`.
  The account number itself is not a field on this model and is not stored

Built in M6A:

- **PaymentIntent**: `booking`, `customer`, `reference`, `amount_kobo`, `currency`,
  `status`, `gateway`, `gateway_reference`, `gateway_status`, `method`,
  `authorization_url`, `idempotency_key`, `paid_at`, `failed_at`
- **WebhookEvent**: `gateway`, `event_id` (unique with gateway), `event_type`,
  `reference`, `amount_kobo`, `currency`, `payload_digest`, `processed_at`,
  `outcome`. The payload itself is not stored
- **PayoutDestination** gains `verification_status`, `resolved_account_name`,
  `verified_at`, `verification_reference`

Built in M6B:

- **PayoutRequest** gains `transfer_reference` (ours, reserved before the call),
  `transfer_provider`, `gateway_reference`, `gateway_status`, `submitted_at`,
  `reconciled_at`
- **FinancialAnomaly**: `kind`, `classification`, `subject_type`, `subject_id`,
  `subject_reference`, `detail`, `first_seen_at`, `last_seen_at`, `times_seen`,
  `resolved_at`, `resolution`. One open row per problem

Still deferred:

- **Transaction** and **SavedAuthorization**, which become meaningful alongside
  refunds and saved cards
- **LedgerEntry**, if and when cash bookings need it

A ledger is how cash would work. On a card booking Sync holds the money and releases
the provider's share on completion; on a cash booking the provider is paid directly,
so commission is owed the other way and would land as a negative entry netting
against future earnings. Neither payment direction exists yet, and building the
general machine before the case that needs it would be guessing at the shape of the
case. What M5 has instead is a settlement per completed booking and a balance summed
from immutable rows, which is enough for money owed and not yet enough for money in
two directions.

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
POST   /api/v1/customer/bookings/{id}/pay        idempotent
GET    /api/v1/customer/payments
GET    /api/v1/customer/payments/{id}
POST   /api/v1/customer/payments/{id}/verify    asks the provider, not the client
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
GET    /api/v1/provider/earnings                 derived, never a stored balance
GET    /api/v1/provider/earnings/settlements
GET    /api/v1/provider/payouts
POST   /api/v1/provider/payouts/request          gated, idempotent, locked
GET    /api/v1/provider/payouts/{id}
POST   /api/v1/provider/payouts/{id}/cancel      the provider's only lifecycle move
GET    /api/v1/provider/payout-destination
PUT    /api/v1/provider/payout-destination
POST   /api/v1/provider/payout-destination/verify   resolves it with the bank
GET    /api/v1/provider/banks
```

There is deliberately no route by which a provider marks a payout processed or paid.
Those transitions exist only in the admin and in the service function a future
transfer adapter will call.

### Machine to machine

```
POST   /api/v1/webhooks/paystack        signature verified, idempotent by event id
```

Unauthenticated, because the caller has no account here. The signature over the
raw body is the authentication, and it is checked before the body is parsed.

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
    ├── payout/[id].tsx
    └── job/[id].tsx
```

The provider surfaces are built but the provider tab bar is not, so `offers`,
`earnings`, `payouts`, `payout/[id]`, `payout-request` and `payout-destination`
currently sit in the one `(app)` group beside the customer screens and are reached
by direct navigation. `pay/[id]`, the customer checkout screen, sits there too and
is reached from the booking it pays for. Splitting the two role stacks is a navigation change on its
own, and doing it inside a domain milestone would mix two kinds of risk.

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
| M5a | Financial domain: booking price snapshot, settlement, commission, derived earnings, payout lifecycle, payout destination | A completed job earns a settlement, a provider sees a balance and requests a payout, with no gateway involved |
| M5b | Payment integration: Paystack charge and webhook, escrow release, transfers, cash and the ledger it needs | Real money in, correct split, real payout out |
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

0. **Nothing is credentialed yet.** Every production adapter now exists, and none
   of them has an account behind it. `SMS_BACKEND`, `EMAIL_BACKEND`,
   `PAYMENT_GATEWAY` and `BANK_RESOLVER` all default to the console or fake
   implementation, so codes print rather than send and payments move no money.
   What is needed is a Paystack account with its keys and webhook URL set, a
   Termii account with an approved sender id, and a Resend account with a
   verified sending domain. That is configuration rather than code, and it is the
   last thing standing between the current build and a customer paying for a real
   booking.

   The capability table is now settled for every capability that exists:
   `CREATE_BOOKING` at phone, `ACCEPT_JOB` and `REQUEST_PAYOUT` at phone plus
   email.

0b. **Money moves in both directions, on fake providers.** M6A took payment in;
   M6B sends it out, through a transfer abstraction with a Paystack adapter
   behind it and a reconciliation path for a submission whose outcome was never
   received. What is missing is the account: `PAYOUT_TRANSFER_PROVIDER` defaults
   to the fake, which submits nothing. Switching it on needs Paystack Transfers
   enabled, a funded balance, and a first payout watched by a person.

0c. **Nothing runs the workers yet.** The tasks, the schedule and the retry
   policy all exist and are tested, but a deployment has to actually start
   `celery -A config worker` and one `celery -A config beat`. Until it does, the
   system behaves exactly as it did at the end of M6A: correct while somebody is
   holding a phone, and inert otherwise.

1. **Local infrastructure.** Docker Compose is the chosen approach and the file is in
   the repository, but Docker Desktop must be installed on each development machine.
2. **Escrow posture.** Holding customer funds between payment and completion is what
   makes the marketplace trustworthy, and it means Sync holds money it does not own.
   This has CBN and licensing implications at scale. The engineering design is the
   same either way. Worth legal advice before the payment integration.
3. **Commission model.** Still open, and deliberately not answered by M5. The
   implementation is one flat rate at 2000 basis points in `PLATFORM_COMMISSION`,
   with the rate applied copied onto each settlement. Per-category remains the
   recommendation, since dispatch and laundry have thin margins where a flat 20
   percent does not work, but it is a pricing decision rather than an engineering
   one. Moving to per-category is a rate column on `Service` read at settlement
   time, which changes one line of `apps/payments/services.py` and no history.
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
| Forged payment webhook | A fake success event would pay a provider for nothing | HMAC over the raw body, then amount and currency checked against our own record |
| Duplicate charge | A retried tap over a bad connection charges twice | Idempotency key, booking row locked, one successful intent per booking enforced by index |
| Wrong bank account | One mistyped digit sends money to a stranger | The account is resolved with the bank and the returned name shown before any payout |
| Duplicate transfer | A retry after a timeout pays a provider twice | Our reference is reserved before the call, a payout carrying one is never resubmitted, and reconciliation establishes what happened |
| Silent inconsistency | Money owed to nobody, or owed twice, noticed months later | An hourly sweep classifies anomalies and repairs only the unambiguous |
| Payout double-spend | Two devices requesting the same balance pays it out twice | Provider row locked, one live payout per provider enforced by a partial unique index, balance derived not stored |
| Payout destination exposure | A stored bank account number is a standing liability | Only a hash and the last four digits persist. The full number is never a field |
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
