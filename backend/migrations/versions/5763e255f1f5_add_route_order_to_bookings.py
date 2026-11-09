"""add route_order to bookings

Revision ID: 5763e255f1f5
Revises: abc123conflict
Create Date: 2026-02-25 13:01:23.483074

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5763e255f1f5'
down_revision = 'abc123conflict'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bookings', sa.Column('route_order', sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('bookings', 'route_order')
