"""add chat messages

Revision ID: e1f2g3h4i5j6
Revises: d9e0f1a2b3c4
Create Date: 2026-01-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e1f2g3h4i5j6'
down_revision = 'd9e0f1a2b3c4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('chat_messages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('booking_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('is_read', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_messages_booking_id'), 'chat_messages', ['booking_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_chat_messages_booking_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
