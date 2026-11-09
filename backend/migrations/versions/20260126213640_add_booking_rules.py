"""add booking rules

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-01-26 21:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd9e0f1a2b3c4'
down_revision = 'c8d9e0f1a2b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('booking_rules',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('provider_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('conditions', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_booking_rules_provider_id'), 'booking_rules', ['provider_id'], unique=False)
    op.create_index(op.f('ix_booking_rules_tenant_id'), 'booking_rules', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_booking_rules_tenant_id'), table_name='booking_rules')
    op.drop_index(op.f('ix_booking_rules_provider_id'), table_name='booking_rules')
    op.drop_table('booking_rules')
