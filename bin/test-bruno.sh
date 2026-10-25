#!/usr/bin/env bash
# Run the Bruno collection, with its assertions, against the real API over a throwaway database
# filled with the agreement's example (backend/tests/fixture_server.py).
#
# Called by `make test-bruno` and by CI. Needs Node, for the pinned Bruno CLI, and the backend
# (`make install`, or PYTHON set to an interpreter that has it).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
python="${PYTHON:-$root/backend/.venv/bin/python}"
port="${BRUNO_PORT:-8597}"
cli="@usebruno/cli@4.2.0"

(cd "$root/backend" && exec "$python" -m tests.fixture_server "$port") &
server=$!
trap 'kill "$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true' EXIT

for attempt in $(seq 1 120); do
  curl -fs -o /dev/null "http://127.0.0.1:$port/api/health" && break
  if [ "$attempt" -eq 120 ]; then
    echo "The fixture server did not answer on port $port." >&2
    exit 1
  fi
  sleep 0.5
done

cd "$root/bruno"
# The CLI is pinned but its dependencies resolve afresh; like the interface's installs
# (frontend/.npmrc), take nothing published in the last two weeks.
# The fixture server's administrator; see backend/tests/fixture_server.py.
npx --yes --min-release-age=14 "$cli" run api -r --env local \
  --env-var "base_url=http://127.0.0.1:$port" \
  --env-var "login=lucia" \
  --env-var "password=correct horse battery"
