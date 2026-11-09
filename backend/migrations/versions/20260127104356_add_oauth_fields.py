"""add oauth fields

Revision ID: h4i5j6k7l8m9
Revises: a6adf4e1a8e1
Create Date: 2026-01-27 10:42:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'h4i5j6k7l8m9'
down_revision = 'e1f2g3h4i5j6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('oauth_provider', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('oauth_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_users_oauth_provider'), 'users', ['oauth_provider'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_oauth_provider'), table_name='users')
    op.drop_column('users', 'oauth_id')
    op.drop_column('users', 'oauth_provider')
