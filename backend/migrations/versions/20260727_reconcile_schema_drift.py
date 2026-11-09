"""Reconcile ORM metadata with the migrated schema.

Revision ID: b15schemadrift
Revises: b14paymenttiming
Create Date: 2026-07-27
"""

from alembic import op

revision = "b15schemadrift"
down_revision = "b14paymenttiming"
branch_labels = None
depends_on = None


_NOT_NULL_COLUMNS = {
    "bookings": ("payment_timing", "deposit_percentage", "discount_cents"),
    "chat_messages": ("is_read", "created_at"),
    "email_campaigns": ("status", "sent_count", "opened_count", "clicked_count", "created_at"),
    "promo_codes": ("current_uses", "min_purchase_cents", "is_active", "created_at"),
    "providers": ("payment_timing_default", "deposit_percentage_default", "accepts_cash", "accepts_card"),
    "referrals": ("reward_cents", "is_rewarded", "created_at"),
    "services": ("peak_hour_multiplier", "weekend_multiplier"),
}


def upgrade() -> None:
    # Historical migrations supplied server defaults without NOT NULL. Backfill
    # any legacy rows before making the model's existing invariants enforceable.
    op.execute(
        """
        UPDATE bookings SET
            payment_timing = COALESCE(payment_timing, 'BEFORE_SERVICE'::paymenttiming),
            deposit_percentage = COALESCE(deposit_percentage, 0),
            discount_cents = COALESCE(discount_cents, 0)
        """
    )
    op.execute(
        """
        UPDATE chat_messages SET
            is_read = COALESCE(is_read, false),
            created_at = COALESCE(created_at, now())
        """
    )
    op.execute(
        """
        UPDATE email_campaigns SET
            status = COALESCE(status, 'draft'),
            sent_count = COALESCE(sent_count, 0),
            opened_count = COALESCE(opened_count, 0),
            clicked_count = COALESCE(clicked_count, 0),
            created_at = COALESCE(created_at, now())
        """
    )
    op.execute(
        """
        UPDATE promo_codes SET
            current_uses = COALESCE(current_uses, 0),
            min_purchase_cents = COALESCE(min_purchase_cents, 0),
            is_active = COALESCE(is_active, true),
            created_at = COALESCE(created_at, now())
        """
    )
    op.execute(
        """
        UPDATE providers SET
            payment_timing_default = COALESCE(payment_timing_default, 'before_service'),
            deposit_percentage_default = COALESCE(deposit_percentage_default, 0),
            accepts_cash = COALESCE(accepts_cash, true),
            accepts_card = COALESCE(accepts_card, true)
        """
    )
    op.execute(
        """
        UPDATE referrals SET
            reward_cents = COALESCE(reward_cents, 0),
            is_rewarded = COALESCE(is_rewarded, false),
            created_at = COALESCE(created_at, now())
        """
    )
    op.execute(
        """
        UPDATE services SET
            peak_hour_multiplier = COALESCE(peak_hour_multiplier, 1.0),
            weekend_multiplier = COALESCE(weekend_multiplier, 1.0)
        """
    )

    for table, columns in _NOT_NULL_COLUMNS.items():
        for column in columns:
            op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" SET NOT NULL')

    op.create_index("idx_referrals_referred", "referrals", ["referred_id"])


def downgrade() -> None:
    op.drop_index("idx_referrals_referred", table_name="referrals")
    for table, columns in reversed(tuple(_NOT_NULL_COLUMNS.items())):
        for column in columns:
            op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP NOT NULL')
