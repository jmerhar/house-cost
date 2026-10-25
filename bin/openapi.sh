#!/usr/bin/env bash
# Export the API's OpenAPI schema, then generate the interface's TypeScript types from it.
#
# Both are committed, so a change to a response shape shows up as a diff in the pull request that
# caused it, and CI (`make contract`) can prove the committed copies are current.
set -euo pipefail

cd "$(dirname "$0")/.."

python="${PYTHON:-backend/.venv/bin/python}"
if ! command -v "$python" >/dev/null 2>&1; then
  echo "No interpreter at '$python'. Run 'make install' first, or set PYTHON." >&2
  exit 1
fi

echo "Exporting the schema to frontend/openapi.json"
"$python" bin/export-openapi.py > frontend/openapi.json

echo "Generating frontend/src/lib/api-types.ts"
# Run as a pinned package of its own rather than installed into the interface: it needs a
# TypeScript major the interface has moved past. Like the interface's installs (frontend/.npmrc),
# it takes nothing published in the last two weeks, and it is fetched through the registry this
# machine's npm reaches outside the project, whose .npmrc names the public one.
registry=$(cd / && npm config get registry)
(cd frontend && npx --yes --registry="$registry" --min-release-age=14 \
  openapi-typescript@7.13.0 openapi.json -o src/lib/api-types.ts)
