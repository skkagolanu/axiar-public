"""Add outbox_messages table for transactional outbox pattern

Revision ID: b11outboxmsg
Revises: b10promoreferraltenant
Create Date: 2026-07-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b11outboxmsg"
down_revision: Union[str, None] = "b10promoreferraltenant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_messages_status_created", "outbox_messages", ["status", "created_at"])
    op.create_index(op.f("ix_outbox_messages_tenant_id"), "outbox_messages", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_outbox_messages_tenant_id"), table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_status_created", table_name="outbox_messages")
    op.drop_table("outbox_messages")
