# House costs

## What this is

A self-hosted app that tracks a shared house's running costs and splits each bill between the
households that share it, by per-category rules that take effect from a date. One container: a
FastAPI backend over SQLite that also serves a Svelte interface.

## Layout

```
backend/src/house_cost/
  config.py        settings from the environment (pydantic-settings)
  db.py            async engine with SQLite's pragmas, the session factory, session_scope
  models/          base.py (Base, UtcDateTime, naming convention), people.py (households,
                   people, sessions), ledger.py (categories, rules, bills, lines, shares,
                   settlements, attachments), admin.py (audit log, settings, reconciliation),
                   papers.py (suppliers, services, library documents)
  money.py         allocate(): whole cents split by largest remainder, adding up exactly
  splitting.py     the rule in force on a date, and a split by basis points
  bills.py         set_lines (splitting a bill's lines, keeping unchanged ones), locked periods
  balances.py      each household's balance, and settle(): the transfers that clear them
  reconciliation.py  a period's bills split again by reconciled shares
  auth.py          argon2 passwords, server-side sessions, the login throttle, the origin check
  passkeys.py      the relying party for a request, and WebAuthn challenges waiting for answers
  audit.py         record() for the audit log; the app's settings and their defaults
  notify/          Notifier: the channels the deployment configures (NOTIFY_EMAIL_URL,
                   NOTIFY_SIGNAL_URL) made into each person's Apprise URLs, and send_to;
                   AppriseSender delivers, behind the Sender protocol; once(); messages.py is the
                   catalogue in each language; events.py decides who hears of a new bill, a
                   price change, a contract ending or a missing bill
  contacts.py      checking an email address, and a phone number into international form
  scheduler.py     the in-process loop: the daily VACUUM INTO backup and the daily reminders,
                   each tick() testable with a given time
  claude.py        the optional Claude client: read_bill, read_terms, ask; the schemas its
                   answers are parsed into, and turning its dates and euros into values
  storage.py       uploaded files under their SHA-256, and recognising their type by content;
                   attachments and library documents share it (attachments.held)
  extraction/      reading bills: pdf.py (a PDF's text layer), atcud.py (the fiscal QR code),
                   ocr.py (Tesseract, and spotting a garbled text layer), text.py (amounts and
                   dates as Portuguese bills write them), parsers.py (one per supplier NIF, and
                   a generic one), pipeline.py (all of it, with where each value came from)
  api/
    app.py         create_app: routers under /api, the write guard, the interface and its SPA
                   fallback
    deps.py        Services (built once per process) and the request dependencies
    schemas.py     every request and response model; the interface's types come from these
    session_cookie.py  issuing and clearing the session cookie, and describing the person
    routers/       one module per resource
  healthcheck.py   `python -m house_cost.healthcheck`, the image's HEALTHCHECK
  __main__.py      `python -m house_cost [--reload]`
backend/alembic/   migrations; bin/entrypoint.sh runs them before the app starts
backend/tests/     pytest; fixture_server.py serves the real app for the Bruno collection,
                   softauthn.py is a software authenticator for the passkey ceremonies,
                   synthetic.py makes the PDFs tests read, in place of real bills,
                   tooling/ tests the scripts in bin/ that have logic of their own
frontend/          Svelte 5, Vite, TypeScript, Paraglide
  src/App.svelte   setup, login, then the routed views
  src/pages/       one component per view; BillForm.svelte enters and corrects a bill
  src/lib/api.ts   the API client; api-types.ts is generated from the API's schema (make openapi)
  src/lib/format.ts  cents and basis points to and from text, dates, in the person's language
  src/lib/router.svelte.ts  path routes over the history API, and in-app link handling
  src/lib/state.svelte.ts   the person logged in, households and categories, shared by views
  src/lib/language.ts  which language: the person's choice, else the browser's, else English
  src/lib/passkeys.ts  the browser's half of the passkey ceremonies, replaceable in tests
  src/testing.ts   a stand-in API answering by method and path, and the agreement's examples
  messages/        en.json and pt-PT.json; Paraglide compiles them into src/paraglide
                   (generated); GLOSSARY.md fixes the words for the main ideas
  openapi.json     the API's schema, committed so `make contract` can prove it current
bruno/             a request, with assertions, for every endpoint (bin/test-bruno.sh)
bin/               every script the Makefile and CI run
CHANGELOG.md       every release's notes; new work goes under `## Unreleased`
```

## Things worth knowing before changing anything

- **A bill line's split is stored when it is saved, never worked out on reading.** The shares
  come from the rule in force on the bill's date (`splitting.rule_in_force`); a later rule,
  even one back-dated, changes nothing already saved. Correcting a bill re-splits only the
  lines whose category or amount changed, or all of them if the date did (`bills.set_lines`).
- **Rules are never edited.** A change is a new rule from a later date, and a rule that has
  split a line cannot be deleted. Shares are basis points adding up to 10 000; money is whole
  cents, split by `money.allocate`, so shares always add up to the amount exactly.
- **A request's database session commits before its response is sent** (`DbDep` has
  `scope="function"`). A yield dependency's default scope would commit after the response, so a
  client acting on it at once, or a background task, could miss what it describes;
  `test_a_requests_changes_are_committed_before_its_answer_starts` checks it.
- **Every write goes through `audit.record`**, in the same transaction, with the API's view of
  the record before and after. The activity log is open to everyone on purpose.
- **Every write under /api needs the `X-Requested-With: house-cost` header, and any Origin must
  be the app's own** (`app._guard_writes`). The interface's client sends it; so must any other.
- **Routers are mounted public or protected in `app.py`.** A protected router needs a session for
  every route; `test_every_route_but_the_public_ones_needs_a_session` sweeps the schema and
  fails on any route that answers without one. Adding a public route means adding it to `PUBLIC`
  in that test.
- **Reconciliation is invisible while it is off**: its routes answer 404, Balances ignores
  adjustments, and closed periods lock nothing.
- **Passkeys belong to the host name of `PUBLIC_URL`** (else the request's own host). Changing
  the address the app is served at orphans every passkey made under the old one.
- **Real bills never go in tests.** Parsers are tested on synthetic PDFs (tests/synthetic.py)
  laid out like the real ones; `make test-samples` reads the real files in the ignored samples/
  directory against samples/expected.json, locally only.
- **What a bill's QR code states wins over the page.** The pipeline records where each value came
  from, and the interface says so; a page total that disagrees is flagged, not trusted.
- **First-run setup is open to whoever arrives first** while no person exists, and closed for good
  after; a new deployment stays unreachable from outside until it is set up.
- **The interface's types come from the API's schema.** Changing a response model means running
  `make openapi` and committing `frontend/openapi.json` and `frontend/src/lib/api-types.ts`;
  `make contract` and CI fail otherwise.
- **The tests build their schema with `create_all`, not the migrations.** `test_migrations.py`
  runs `alembic upgrade head` and compares the result with the models, so a model change without
  a migration (`make revision m="..."`) fails there.
- **An unknown path under `/api` is a 404, never the interface's shell.** The SPA fallback in
  `app.py` serves `index.html` for client-side routes only.
- **The image runs read-only as user 1000.** The app writes only to `/data` and `/tmp`, and Python
  writes no bytecode (`PYTHONDONTWRITEBYTECODE`).
- **The lockfile records only the public npm registry.** Regenerate it with `make lockfile`, never
  a plain `npm install`; `bin/check-lockfile.sh` guards it.
- **Notifications are sent after the request, never inside it.** A new bill is committed before
  its notification is scheduled, and `notify.events` logs its own failures, so a failed delivery
  cannot fail a save. Scheduled ones are sent once each, keyed in `sent_notification` by what
  they are about (`notify.once`).
- **A person's email address and phone number are seen only by admins and themselves.**
  `PersonDetail` carries them (None for anyone else); `PersonOut`, which the audit log records,
  never does. The channels' URLs can hold credentials and stay in the environment, never in the
  database or the logs.
- **Notification text lives in `notify/messages.py`, not Paraglide**, since the server sends it;
  every key needs both languages with the same placeholders, which a test checks.
- **Claude only fills gaps and only proposes.** In bill reading it is asked when no parser knows
  the issuer or a core field is missing, and `pipeline.merge_claude` never replaces what the QR
  code or the page gave. Without a key `Services.claude` is None, the routes answer 404
  `claude_off`, and `Me.claude_enabled` hides the interface. Tests drive the real SDK through
  `httpx2.MockTransport` (tests/test_claude.py); the SDK uses httpx2, so respx cannot see it.
- **Real bills and contracts never enter the repository.** They hold names, tax numbers and bank
  details; `samples/` is ignored for local runs only.

## Commands

```bash
make install        # backend/.venv and frontend/node_modules
make dev            # API :8000 + Vite :5173 with hot reload
make test           # both suites; ARGS=... passes through to pytest or vitest
make coverage       # both suites with coverage and the combined summary
make test-samples   # read the real bills in samples/ (ignored by git) against expected.json
make lint           # shellcheck, ruff, lockfile, versions, compose files
make contract       # the committed schema and generated types are current
make check          # all of the above and the Bruno collection: gate a commit on this
make revision m="what changed"   # generate a migration from the models
make release VERSION=X.Y.Z       # then push main and the tag
```

## Testing conventions

- Two coverage suites, gated in `coverage.toml` just under what is measured. Raise a gate as
  coverage climbs; never lower one.
- Each backend test gets its own data directory and SQLite file (`conftest.py`).
- A new test should fail when the code it covers is broken: mutate the code and watch it fail
  before trusting it.
- Every message in `frontend/messages/en.json` has a Portuguese translation with the same
  placeholders (`src/messages.test.ts`).
