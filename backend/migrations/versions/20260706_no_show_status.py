"""Add NO_SHOW and normalize granular booking-state labels to the ORM enum names.

Revision ID: b12noshow
Revises: b11outboxmsg
Create Date: 2026-07-06
"""

from alembic import op

revision = "b12noshow"
down_revision = "b11outboxmsg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'NO_SHOW'")
    # Fix: these were added lowercase by b5granularstatus but the ORM only ever
    # sends the uppercase .name -- add the values it actually needs.
    op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'ON_MY_WAY'")
    op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'ARRIVED'")
    op.execute("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'DELAYED'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; a full recreate is needed.
    # Acceptable for dev; prod rollback would require a data migration first.
    pass
