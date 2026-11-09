"""Add tenant_id to promo_codes and referrals

Revision ID: b10promoreferraltenant
Revises: b9tenantsettings
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b10promoreferraltenant"
down_revision: Union[str, None] = "b9tenantsettings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("promo_codes", sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_promo_codes_tenant_id"), "promo_codes", ["tenant_id"])
    op.create_foreign_key(None, "promo_codes", "tenants", ["tenant_id"], ["id"])
    op.execute("UPDATE promo_codes SET tenant_id = (SELECT id FROM tenants ORDER BY created_at ASC LIMIT 1)")
    op.alter_column("promo_codes", "tenant_id", nullable=False)

    op.add_column("referrals", sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_referrals_tenant_id"), "referrals", ["tenant_id"])
    op.create_foreign_key(None, "referrals", "tenants", ["tenant_id"], ["id"])
    op.execute("UPDATE referrals SET tenant_id = (SELECT id FROM tenants ORDER BY created_at ASC LIMIT 1)")
    op.alter_column("referrals", "tenant_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint(None, "promo_codes", type_="foreignkey")
    op.drop_index(op.f("ix_promo_codes_tenant_id"), table_name="promo_codes")
    op.drop_column("promo_codes", "tenant_id")
    op.drop_constraint(None, "referrals", type_="foreignkey")
    op.drop_index(op.f("ix_referrals_tenant_id"), table_name="referrals")
    op.drop_column("referrals", "tenant_id")