"""fix is_rewarded to boolean

Revision ID: 20260225_170500
Revises: merge001
Create Date: 2026-02-25 17:05:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260225_170500'
down_revision = 'merge001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change is_rewarded from integer to boolean
    op.execute("ALTER TABLE referrals ALTER COLUMN is_rewarded TYPE BOOLEAN USING is_rewarded::boolean")


def downgrade() -> None:
    # Change back to integer
    op.execute("ALTER TABLE referrals ALTER COLUMN is_rewarded TYPE INTEGER USING is_rewarded::integer")
