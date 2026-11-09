"""Add granular field statuses to bookingstatus enum

New values: on_my_way, arrived, delayed

Revision ID: b5granularstatus
Revises: tenantcols02
Create Date: 2026-06-30
"""

import sqlalchemy as sa
from alembic import op

revision = "b5granularstatus"
down_revision = "tenantcols02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL requires ALTER TYPE ... ADD VALUE (cannot be in a transaction for older PG,
    # but PG 12+ supports it; use execute for clarity).
    op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'on_my_way'")
    op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'arrived'")
    op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'delayed'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; a full recreate is needed.
    # Acceptable for dev; prod rollback would require a data migration first.
    pass
