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
- **Reads bills.** Upload a bill's PDF or a photo, and the form opens filled in from its fiscal
  QR code and its text, to be checked before saving.
- **Keeps the paperwork.** A bill's PDF or a photo of it, a receipt for each transfer, and a
  library of contracts and terms searched by their text.
- **Knows the contracts.** Each service's references, when it ends or renews, its lock-in and
  notice period.
- **Reports by year, category and month**, with a CSV export of every bill line.
- **Records every change**: who added, corrected or deleted what, visible to everyone.
- **Optional annual reconciliation**: split a closed period's bills again by shares agreed at its
  end, and settle the difference.
- **Notifications by email and Signal**, each person giving an address or a phone number and
  choosing which: a bill another household adds, a unit price that changed, a contract ending or
  a lock-in expiring in 30 and 7 days, and a regular bill that has not arrived.
- **Passkeys**: log in with a fingerprint, face or screen lock instead of a password.
- **Claude, optionally**: with an Anthropic API key, Claude reads the bills whose layout the app
  does not know, proposes a contract's dates and notice for its service, and answers questions
  about a document with the pages it rests on. The file in question is sent to Anthropic's API.
- **In English and Portuguese**, on a phone or a computer, and installable on a phone's home
  screen as an app ("Add to Home Screen").

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
| `TZ` | `UTC` | Time zone of the house: log lines, the daily backup and reminders follow it. |
| `BACKUP_TIME` | `03:30` | From when each day the database is copied to `data/backups`. |
| `BACKUPS_KEPT` | `14` | How many daily copies are kept. |
| `NOTIFY_EMAIL_URL` | | Apprise URL notifications are mailed through, without a recipient. |
| `NOTIFY_SIGNAL_URL` | | Apprise Signal URL (a signal-cli REST API and its number) messages are sent from. |
| `PHONE_COUNTRY_CODE` | `351` | The country a phone number typed without a country code is in. |
| `ANTHROPIC_API_KEY` | | Turns on Claude. Leave it unset to keep every file on the server. |
| `ANTHROPIC_API_KEY_FILE` | | A file holding the key, such as a Docker secret, in place of the variable. |
| `CLAUDE_MODEL` | `claude-opus-5-5` | The model Claude's requests use. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |

Everything the app keeps is in `./data`. Back that directory up and there is nothing else to keep;
`data/backups` holds a consistent copy of the database from each day, so a backup that catches
the live database mid-write still has one to restore.

Notifications go out through [Apprise](https://github.com/caronc/apprise), by channels the
deployment configures without a recipient; each person's email address and phone number, set
on the account page or by an administrator, complete them. A channel left unset is not
offered. For example:

```yaml
NOTIFY_EMAIL_URL: mailto://user:password@smtp.example.com:587/?from=costs@example.com
NOTIFY_SIGNAL_URL: signal://signal-cli-rest-api:8080/+351210000000
```

The address is added as the mail URL's `to`, and the phone number to the end of the Signal URL's
path, so any Apprise service that takes its recipient there works too. The container needs to
reach what the URLs name.

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
