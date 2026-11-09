"""add business features

Revision ID: bf001_business
Revises: abc123conflict
Create Date: 2026-02-25 16:35:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'bf001_business'
down_revision = 'abc123conflict'
branch_labels = None
depends_on = None


def upgrade():
    # Check and add columns only if they don't exist
    from sqlalchemy import inspect
    from app.core.database import db_manager
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Bookings - Payment timing
    existing_columns = [c['name'] for c in inspector.get_columns('bookings')]
    
    if 'payment_timing' not in existing_columns:
        op.add_column('bookings', sa.Column('payment_timing', sa.String(20), server_default='before_service'))
    if 'deposit_percentage' not in existing_columns:
        op.add_column('bookings', sa.Column('deposit_percentage', sa.Integer(), server_default='0'))
    if 'promo_code' not in existing_columns:
        op.add_column('bookings', sa.Column('promo_code', sa.String(50), nullable=True))
    if 'discount_cents' not in existing_columns:
        op.add_column('bookings', sa.Column('discount_cents', sa.Integer(), server_default='0'))

    # Providers - Payment settings
    provider_columns = [c['name'] for c in inspector.get_columns('providers')]
    
    if 'payment_timing_default' not in provider_columns:
        op.add_column('providers', sa.Column('payment_timing_default', sa.String(20), server_default='before_service'))
    if 'deposit_percentage_default' not in provider_columns:
        op.add_column('providers', sa.Column('deposit_percentage_default', sa.Integer(), server_default='0'))
    if 'accepts_cash' not in provider_columns:
        op.add_column('providers', sa.Column('accepts_cash', sa.Boolean(), server_default='true'))
    if 'accepts_card' not in provider_columns:
        op.add_column('providers', sa.Column('accepts_card', sa.Boolean(), server_default='true'))

    # Services - Dynamic pricing
    service_columns = [c['name'] for c in inspector.get_columns('services')]
    
    if 'peak_hour_multiplier' not in service_columns:
        op.add_column('services', sa.Column('peak_hour_multiplier', sa.Float(), server_default='1.0'))
    if 'weekend_multiplier' not in service_columns:
        op.add_column('services', sa.Column('weekend_multiplier', sa.Float(), server_default='1.0'))
    if 'min_price_cents' not in service_columns:
        op.add_column('services', sa.Column('min_price_cents', sa.Integer(), nullable=True))
    if 'max_price_cents' not in service_columns:
        op.add_column('services', sa.Column('max_price_cents', sa.Integer(), nullable=True))
    if 'availability_schedule' not in service_columns:
        op.add_column('services', sa.Column('availability_schedule', postgresql.JSONB(), nullable=True))
    if 'blackout_dates' not in service_columns:
        op.add_column('services', sa.Column('blackout_dates', postgresql.JSONB(), nullable=True))

    # Check if tables exist before creating
    existing_tables = inspector.get_table_names()
    
    # Promo codes table
    if 'promo_codes' not in existing_tables:
        op.create_table(
            'promo_codes',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('code', sa.String(50), unique=True, nullable=False),
            sa.Column('discount_type', sa.String(20), nullable=False),
            sa.Column('discount_value', sa.Integer(), nullable=False),
            sa.Column('max_uses', sa.Integer(), nullable=True),
            sa.Column('current_uses', sa.Integer(), server_default='0'),
            sa.Column('min_purchase_cents', sa.Integer(), server_default='0'),
            sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
            sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )
        op.create_index('idx_promo_codes_code', 'promo_codes', ['code'])

    # Referrals table
    if 'referrals' not in existing_tables:
        op.create_table(
            'referrals',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('referrer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('referred_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('referral_code', sa.String(20), nullable=False),
            sa.Column('reward_cents', sa.Integer(), server_default='0'),
            sa.Column('is_rewarded', sa.Boolean(), server_default='false'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )
        op.create_index('idx_referrals_referrer', 'referrals', ['referrer_id'])
        op.create_index('idx_referrals_code', 'referrals', ['referral_code'])

    # Email campaigns table
    if 'email_campaigns' not in existing_tables:
        op.create_table(
            'email_campaigns',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('subject', sa.String(500), nullable=False),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('segment', sa.String(50), nullable=True),
            sa.Column('status', sa.String(20), server_default='draft'),
            sa.Column('sent_count', sa.Integer(), server_default='0'),
            sa.Column('opened_count', sa.Integer(), server_default='0'),
            sa.Column('clicked_count', sa.Integer(), server_default='0'),
            sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )


def downgrade():
    # Drop tables
    op.drop_table('email_campaigns')
    op.drop_table('referrals')
    op.drop_table('promo_codes')

    # Remove columns from services
    op.drop_column('services', 'blackout_dates')
    op.drop_column('services', 'availability_schedule')
    op.drop_column('services', 'max_price_cents')
    op.drop_column('services', 'min_price_cents')
    op.drop_column('services', 'weekend_multiplier')
    op.drop_column('services', 'peak_hour_multiplier')

    # Remove columns from providers
    op.drop_column('providers', 'accepts_card')
    op.drop_column('providers', 'accepts_cash')
    op.drop_column('providers', 'deposit_percentage_default')
    op.drop_column('providers', 'payment_timing_default')

    # Remove columns from bookings
    op.drop_column('bookings', 'discount_cents')
    op.drop_column('bookings', 'promo_code')
    op.drop_column('bookings', 'deposit_percentage')
    op.drop_column('bookings', 'payment_timing')
