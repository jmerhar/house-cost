#!/usr/bin/env bash
# Type-check the interface and run its tests with coverage.
#
# Called by `make test-frontend`, by bin/coverage.sh and by CI. node_modules must already be
# there: CI installs it with `npm ci`, and `make install` does locally (through whatever registry
# this machine's npm is configured with, without touching the lockfile). Arguments are passed
# through to vitest.
set -euo pipefail

cd "$(dirname "$0")/../frontend"
if [ ! -d node_modules ]; then
  echo "frontend/node_modules is missing; run 'make install'." >&2
  exit 1
fi
node build/compile-messages.ts
npx svelte-check --tsconfig ./tsconfig.json --fail-on-warnings
npx vitest run --coverage "$@"
