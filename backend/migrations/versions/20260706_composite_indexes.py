"""Index tenant/provider booking lookups, customer history and external payment intents.

Revision ID: b13compositeidx
Revises: b12noshow
Create Date: 2026-07-06
"""

from alembic import op

revision = "b13compositeidx"
down_revision = "b12noshow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_payments_stripe_payment_intent_id",
        "payments",
        ["stripe_payment_intent_id"],
    )
    op.create_index(
        "ix_bookings_tenant_provider_status",
        "bookings",
        ["tenant_id", "provider_id", "status"],
    )
    op.create_index(
        "ix_bookings_tenant_customer_scheduled",
        "bookings",
        ["tenant_id", "customer_id", "scheduled_time"],
    )
    op.create_index(
        "ix_bookings_tenant_provider_scheduled",
        "bookings",
        ["tenant_id", "provider_id", "scheduled_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_tenant_provider_scheduled", table_name="bookings")
    op.drop_index("ix_bookings_tenant_customer_scheduled", table_name="bookings")
    op.drop_index("ix_bookings_tenant_provider_status", table_name="bookings")
    op.drop_index("ix_payments_stripe_payment_intent_id", table_name="payments")
