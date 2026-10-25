# House costs

[![Test and Publish](https://github.com/jmerhar/house-cost/actions/workflows/build-and-push.yml/badge.svg)](https://github.com/jmerhar/house-cost/actions/workflows/build-and-push.yml)
[![codecov](https://codecov.io/gh/jmerhar/house-cost/branch/main/graph/badge.svg)](https://app.codecov.io/gh/jmerhar/house-cost)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

A self-hosted app for a house whose running costs are shared between households: electricity,
water, internet, upkeep. Each bill is split as it arrives, by rules the households agreed, and
everyone can see what they have paid, what they owe and to whom.

## Running it

```bash
mkdir -p house-cost/data && cd house-cost
curl -O https://raw.githubusercontent.com/jmerhar/house-cost/main/docker-compose.yml
docker compose up -d
```

- **`data` is created first** because Docker would otherwise create it as root.
- **The container runs as user 1000:1000.** If that user cannot write `data`, put
  `HOUSE_COST_UID=$(id -u)` and `HOUSE_COST_GID=$(id -g)` in a `.env` file beside the compose file.
- **It listens on `127.0.0.1:8000`.** Put a reverse proxy that terminates TLS in front of it to
  reach it from elsewhere.

## Configuration

Set in the compose file's environment, or in `.env` beside it.

| Variable | Default | |
|---|---|---|
| `HOUSE_COST_BIND` | `127.0.0.1` | Address the port is published on. |
| `HOUSE_COST_PORT` | `8000` | Port published on the host. |
| `TZ` | `UTC` | Time zone for log lines and scheduled jobs. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |

Everything the app keeps is in `./data`. Back that directory up and there is nothing else to keep.

## Development

```bash
make install   # backend virtualenv and the interface's packages
make dev       # API on :8000 and the interface with hot reload on :5173
make check     # every lint, test, coverage gate and the Bruno collection
make help      # everything else
```

The backend is Python (FastAPI, SQLAlchemy, SQLite); the interface is Svelte with TypeScript,
in English and Portuguese. [CLAUDE.md](CLAUDE.md) describes the layout and the conventions.

## Licence

[GPL-3.0](LICENSE).
