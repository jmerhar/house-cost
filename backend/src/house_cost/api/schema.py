"""The app as the OpenAPI export builds it."""

from pathlib import Path

from fastapi import FastAPI

from house_cost.api.app import create_app
from house_cost.config import Settings


def build_app(data_dir: Path) -> FastAPI:
    """Build the app for exporting its schema: data in a scratch directory, no built interface.

    Named in devtools.toml's [openapi] table. Building the app opens no database connection.
    """
    return create_app(Settings(data_dir=data_dir, static_dir=None))
