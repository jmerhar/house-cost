"""Serve the real application over a throwaway data directory, for the Bruno collection.

    python -m tests.fixture_server PORT

Run from backend/ by bin/test-bruno.sh. The database is migrated exactly as the container's
entrypoint migrates it, so the collection exercises the schema a deployment has.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import uvicorn

from house_cost.api.app import create_app
from house_cost.config import Settings

BACKEND = Path(__file__).resolve().parents[1]


def main(port: int) -> None:
    """Migrate a fresh database and serve the API on loopback until interrupted."""
    with tempfile.TemporaryDirectory() as scratch:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env={"DATA_DIR": scratch, "PATH": ""},
            check=True,
        )
        app = create_app(Settings(data_dir=Path(scratch), static_dir=None))
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main(int(sys.argv[1]))
