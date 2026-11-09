"""Scope booking exclusion to tenant and capacity-occupying states.

Revision ID: b16bookingcapacity
Revises: b15schemadrift
"""

from alembic import op

revision = "b16bookingcapacity"
down_revision = "b15schemadrift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A fresh upgrade runs earlier ALTER TYPE revisions in the same transaction.
    # PostgreSQL requires those enum additions to commit before a predicate uses them.
    with op.get_context().autocommit_block():
        pass
    # The original unconditional exclusion also blocked cancellation/rebooking.
    # Keep the DB safeguard against out-of-band writes, including travelling states.
    op.execute("ALTER TABLE bookings DROP CONSTRAINT no_overlapping_bookings")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT no_overlapping_bookings
        EXCLUDE USING GIST (
            tenant_id WITH =,
            provider_id WITH =,
            booking_time_range(scheduled_time, duration_minutes) WITH &&
        ) WHERE (status IN ('PENDING', 'CONFIRMED', 'ASSIGNED', 'ON_MY_WAY',
                            'ARRIVED', 'DELAYED', 'IN_PROGRESS'))
        """
    )


def downgrade() -> None:
    # This may fail if slots have been reused after cancellation. PostgreSQL then
    # rolls back the migration; operators must reconcile history before downgrading.
    op.execute("ALTER TABLE bookings DROP CONSTRAINT no_overlapping_bookings")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT no_overlapping_bookings
        EXCLUDE USING GIST (
            provider_id WITH =,
            booking_time_range(scheduled_time, duration_minutes) WITH &&
        )
        """
    )
