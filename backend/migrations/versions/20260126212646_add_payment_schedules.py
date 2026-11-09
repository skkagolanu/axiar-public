"""add payment schedules

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-01-26 21:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c8d9e0f1a2b3'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('payment_schedules',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('booking_id', sa.UUID(), nullable=False),
    sa.Column('milestone_name', sa.String(length=255), nullable=False),
    sa.Column('amount_cents', sa.Integer(), nullable=False),
    sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'PAID', 'OVERDUE', 'CANCELLED', name='paymentschedulestatus'), nullable=False),
    sa.Column('payment_id', sa.UUID(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payment_schedules_booking_id'), 'payment_schedules', ['booking_id'], unique=False)
    op.create_index(op.f('ix_payment_schedules_due_date'), 'payment_schedules', ['due_date'], unique=False)
    op.create_index(op.f('ix_payment_schedules_tenant_id'), 'payment_schedules', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_payment_schedules_tenant_id'), table_name='payment_schedules')
    op.drop_index(op.f('ix_payment_schedules_due_date'), table_name='payment_schedules')
    op.drop_index(op.f('ix_payment_schedules_booking_id'), table_name='payment_schedules')
    op.drop_table('payment_schedules')
    op.execute('DROP TYPE paymentschedulestatus')
