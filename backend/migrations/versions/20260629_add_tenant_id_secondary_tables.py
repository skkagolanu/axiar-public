"""Add nullable, indexed tenant references to expenses, reviews, chat messages and campaigns.

Revision ID: tenantcols02
Revises: tenantidrepair01
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "tenantcols02"
down_revision = "tenantidrepair01"
branch_labels = None
depends_on = None

_TABLES = ["expenses", "reviews", "chat_messages", "email_campaigns"]


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("tenant_id", UUID(as_uuid=True), nullable=True))
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.create_foreign_key(f"fk_{table}_tenant_id", table, "tenants", ["tenant_id"], ["id"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"fk_{table}_tenant_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
