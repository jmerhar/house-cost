"""Alembic environment: jigkit's, pointed at house-cost's database and models.

jigkit runs the migrations through the application's own engine and settings, with SQLite's
foreign keys off while a table is rebuilt (so rebuilding ``person`` keeps everyone's passkeys,
sessions and audit entries) and checked afterwards.
"""

from jigkit.migrations import run_migrations

from house_cost.config import get_settings
from house_cost.models import Base

run_migrations(get_settings().resolved_database_url, Base.metadata)
