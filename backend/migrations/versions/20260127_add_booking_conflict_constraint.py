"""add booking conflict constraint

Revision ID: abc123conflict
Revises: 
Create Date: 2026-01-27 16:00:00

"""
from alembic import op


# revision identifiers
revision = 'abc123conflict'
down_revision = 'h4i5j6k7l8m9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add exclusion constraint to prevent overlapping bookings at database level
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")
    
    # Create immutable function for time range calculation
    op.execute("""
        CREATE OR REPLACE FUNCTION booking_time_range(start_time timestamptz, duration int)
        RETURNS tstzrange
        LANGUAGE sql
        IMMUTABLE
        AS $$
            SELECT tstzrange(start_time, start_time + (duration || ' minutes')::interval);
        $$;
    """)
    
    # Add exclusion constraint using the immutable function
    op.execute("""
        ALTER TABLE bookings 
        ADD CONSTRAINT no_overlapping_bookings 
        EXCLUDE USING GIST (
            provider_id WITH =,
            booking_time_range(scheduled_time, duration_minutes) WITH &&
        );
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS no_overlapping_bookings;")
    op.execute("DROP FUNCTION IF EXISTS booking_time_range(timestamptz, int);")

