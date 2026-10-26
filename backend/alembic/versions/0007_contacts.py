"""contacts: an email address and a phone number in place of Apprise URLs

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26 18:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("email", sa.String(length=254), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("phone", sa.String(length=20), nullable=False, server_default="")
        )
        batch_op.drop_column("apprise_urls")


def downgrade() -> None:
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.add_column(sa.Column("apprise_urls", sa.Text(), nullable=False, server_default=""))
        batch_op.drop_column("phone")
        batch_op.drop_column("email")
