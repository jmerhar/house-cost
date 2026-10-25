#!/usr/bin/env sh
# The container's entrypoint: bring the database up to date, then serve.
#
# Migrations run here rather than from the application so that a container which fails to
# migrate never starts serving, and says why.
#
# sh, not bash: the image has no bash.
set -eu

cd /app
echo "house-cost: applying database migrations"
python -m alembic upgrade head

echo "house-cost: starting"
exec python -m house_cost "$@"
