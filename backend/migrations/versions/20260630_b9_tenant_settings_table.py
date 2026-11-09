"""Add tenant_settings table

Revision ID: b9tenantsettings
Revises: b8disputes
Create Date: 2026-06-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b9tenantsettings"
down_revision = "b8disputes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("key", sa.String(100), nullable=False, index=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "key", name="uq_tenant_settings_tenant_key"),
    )


def downgrade() -> None:
    op.drop_table("tenant_settings")
