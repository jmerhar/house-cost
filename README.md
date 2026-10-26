# House costs

[![Test and Publish](https://github.com/jmerhar/house-cost/actions/workflows/build-and-push.yml/badge.svg)](https://github.com/jmerhar/house-cost/actions/workflows/build-and-push.yml)
[![codecov](https://codecov.io/gh/jmerhar/house-cost/branch/main/graph/badge.svg)](https://app.codecov.io/gh/jmerhar/house-cost)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

A self-hosted app for a house whose running costs are shared between households: electricity,
water, internet, upkeep. Each bill is split as it arrives, by rules the households agreed, and
everyone can see what they have paid, what they owe and to whom.

## What it does

- **Splits every bill by the rules in force on its date.** Each category (electricity, road
  upkeep) has a split rule, a percentage per household, from a date on. A change is a new rule
  from a later date, so bills already split keep their split. A bill can have several lines in
  different categories, such as an invoice mixing shared internet with someone's own phone.
- **Shows who owes whom.** What each household has paid, its share, and the transfers that would
  settle everyone up, which can then be recorded as settlements.
- **Keeps the paperwork.** A bill's PDF or a photo of it, and a receipt for each transfer.
- **Reports by year, category and month**, with a CSV export of every bill line.
- **Records every change**: who added, corrected or deleted what, visible to everyone.
- **Optional annual reconciliation**: split a closed period's bills again by shares agreed at its
  end, and settle the difference.
- **Passkeys**: log in with a fingerprint, face or screen lock instead of a password.
- **In English and Portuguese**, on a phone or a computer.

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
  reach it from elsewhere, and set `PUBLIC_URL` to the address it serves the app at.

Open the app and the first person to arrive sets it up: their household and an administrator
login. Do that before anyone else can reach it. The administrator then adds the other
households, the people who log in, and the categories with their split rules.

## Configuration

Set in the compose file's environment, or in `.env` beside it.

| Variable | Default | |
|---|---|---|
| `HOUSE_COST_BIND` | `127.0.0.1` | Address the port is published on. |
| `HOUSE_COST_PORT` | `8000` | Port published on the host. |
| `PUBLIC_URL` | | The address people open the app at, such as `https://costs.example.com`. Writes from any other origin are refused. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1,172.16.0.0/12` | Proxies whose `X-Forwarded-For` and `X-Forwarded-Proto` are believed: addresses or networks (uvicorn's setting). Not `*`, which lets a client choose the address the login throttle counts. |
| `COOKIE_SECURE` | | `true` or `false` to force the session cookie's Secure flag; unset, it follows the request's scheme. |
| `MAX_UPLOAD_BYTES` | `20971520` | The largest file that can be attached. |
| `LOGIN_ATTEMPTS_PER_MINUTE` | `10` | Failed logins allowed per address per minute. |
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
