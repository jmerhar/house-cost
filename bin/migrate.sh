#!/usr/bin/env bash
# Apply migrations to the local development database.
#
# Arguments are passed to alembic, so this also creates one:
#   bin/migrate.sh revision --autogenerate -m "add a column"
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/backend"
python="${PYTHON:-.venv/bin/python}"
# The development database is the one the dev stack mounts and `make db-shell` opens.
export DATA_DIR="${DATA_DIR:-$root/data}"

# Defaulted with `set --` rather than "${@:-upgrade head}", which would pass the whole thing
# as one argument and leave alembic looking for a command called "upgrade head".
if [ "$#" -eq 0 ]; then
  set -- upgrade head
fi

exec "$python" -m alembic "$@"
