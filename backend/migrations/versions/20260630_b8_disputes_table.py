"""Add disputes table

Revision ID: b8disputes
Revises: b5granularstatus
Create Date: 2026-06-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8disputes"
down_revision = "b5granularstatus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'disputestatus') THEN
                CREATE TYPE disputestatus AS ENUM ('open', 'under_review', 'resolved', 'closed');
            END IF;
        END$$;
        """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'disputereason') THEN
                CREATE TYPE disputereason AS ENUM (
                    'service_not_rendered', 'quality_issue', 'overcharge',
                    'no_show_provider', 'other'
                );
            END IF;
        END$$;
        """)
    op.create_table(
        "disputes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False, index=True),
        sa.Column("raised_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("evidence_urls", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("disputes")
    op.execute("DROP TYPE IF EXISTS disputestatus")
    op.execute("DROP TYPE IF EXISTS disputereason")
