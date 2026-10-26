#!/usr/bin/env python3
"""Print the application's OpenAPI schema.

Built from the app itself rather than written by hand, so the schema cannot describe a response
the code does not return. Building the app opens no database connection.
"""

import json
import sys
import tempfile
from pathlib import Path

from house_cost.api.app import create_app
from house_cost.config import Settings


def main() -> None:
    """Write the schema to stdout, keys sorted so the committed copy diffs cleanly."""
    with tempfile.TemporaryDirectory() as scratch:
        app = create_app(Settings(data_dir=Path(scratch), static_dir=None))
        schema = app.openapi()
        # The committed schema describes the API's shape, not a release: a fixed version keeps
        # it from changing with every release or with whichever version happens to be installed.
        schema["info"]["version"] = "0.0.0"
        json.dump(schema, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
