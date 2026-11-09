"""Convert booking payment timing to the PostgreSQL enum.
Enum labels follow SQLAlchemy member names: BEFORE_SERVICE, AFTER_SERVICE and SPLIT_PAYMENT.

Revision ID: b14paymenttiming
Revises: b13compositeidx
Create Date: 2026-07-07
"""

from alembic import op

revision = "b14paymenttiming"
down_revision = "b13compositeidx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE paymenttiming AS ENUM " "('BEFORE_SERVICE', 'AFTER_SERVICE', 'SPLIT_PAYMENT')")
    op.execute("""
        ALTER TABLE bookings
        ALTER COLUMN payment_timing DROP DEFAULT,
        ALTER COLUMN payment_timing TYPE paymenttiming
            USING UPPER(payment_timing)::paymenttiming,
        ALTER COLUMN payment_timing SET DEFAULT 'BEFORE_SERVICE'::paymenttiming
        """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE bookings
        ALTER COLUMN payment_timing DROP DEFAULT,
        ALTER COLUMN payment_timing TYPE VARCHAR(20)
            USING LOWER(payment_timing::text),
        ALTER COLUMN payment_timing SET DEFAULT 'before_service'
        """)
    op.execute("DROP TYPE IF EXISTS paymenttiming")
