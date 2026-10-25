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
  models/          the tables; base.py holds Base, UtcDateTime and the naming convention
  api/
    app.py         create_app: routers under /api, the built interface and its SPA fallback
    deps.py        Services (built once per process) and the request dependencies
    routers/       one module per resource
  healthcheck.py   `python -m house_cost.healthcheck`, the image's HEALTHCHECK
  __main__.py      `python -m house_cost [--reload]`
backend/alembic/   migrations; bin/entrypoint.sh runs them before the app starts
backend/tests/     pytest; fixture_server.py serves the real app for the Bruno collection,
                   tooling/ tests the scripts in bin/ that have logic of their own
frontend/          Svelte 5, Vite, TypeScript, Paraglide
  src/lib/api.ts   the API client; api-types.ts is generated from the API's schema (make openapi)
  src/lib/language.ts  which language: the person's choice, else the browser's, else English
  messages/        en.json and pt-PT.json; Paraglide compiles them into src/paraglide (generated)
  openapi.json     the API's schema, committed so `make contract` can prove it current
bruno/             a request, with assertions, for every endpoint (bin/test-bruno.sh)
bin/               every script the Makefile and CI run
CHANGELOG.md       every release's notes; new work goes under `## Unreleased`
```

## Things worth knowing before changing anything

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
- **Real bills and contracts never enter the repository.** They hold names, tax numbers and bank
  details; `samples/` is ignored for local runs only.

## Commands

```bash
make install        # backend/.venv and frontend/node_modules
make dev            # API :8000 + Vite :5173 with hot reload
make test           # both suites; ARGS=... passes through to pytest or vitest
make coverage       # both suites with coverage and the combined summary
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
