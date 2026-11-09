"""Restore foreign keys, indexes and non-null tenant columns on bookings and providers.

Revision ID: tenantidrepair01
Revises: 20260225_170500
Create Date: 2026-06-29
"""
from alembic import op


revision = "tenantidrepair01"
down_revision = "20260225_170500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Backfill NULL tenant_id to the default tenant (no-op if already populated).
    op.execute(
        """
        UPDATE bookings
        SET tenant_id = (SELECT id FROM tenants WHERE slug = 'default' LIMIT 1)
        WHERE tenant_id IS NULL;
        """
    )
    op.execute(
        """
        UPDATE providers
        SET tenant_id = (SELECT id FROM tenants WHERE slug = 'default' LIMIT 1)
        WHERE tenant_id IS NULL;
        """
    )

    # 2) Enforce NOT NULL (will fail loudly if any tenant_id is still NULL, i.e. no
    #    default tenant existed — surface that rather than silently allow orphans).
    op.alter_column("bookings", "tenant_id", nullable=False)
    op.alter_column("providers", "tenant_id", nullable=False)

    # 3) Restore the FK to tenants(id) if it isn't present.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_bookings_tenant_id') THEN
                ALTER TABLE bookings
                    ADD CONSTRAINT fk_bookings_tenant_id FOREIGN KEY (tenant_id) REFERENCES tenants(id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_providers_tenant_id') THEN
                ALTER TABLE providers
                    ADD CONSTRAINT fk_providers_tenant_id FOREIGN KEY (tenant_id) REFERENCES tenants(id);
            END IF;
        END $$;
        """
    )

    # 4) Restore the index used for tenant-scoped queries (matches the ORM's ix_* naming).
    op.execute("CREATE INDEX IF NOT EXISTS ix_bookings_tenant_id ON bookings (tenant_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_providers_tenant_id ON providers (tenant_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bookings_tenant_id;")
    op.execute("DROP INDEX IF EXISTS ix_providers_tenant_id;")
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS fk_bookings_tenant_id;")
    op.execute("ALTER TABLE providers DROP CONSTRAINT IF EXISTS fk_providers_tenant_id;")
    op.alter_column("providers", "tenant_id", nullable=True)
    op.alter_column("bookings", "tenant_id", nullable=True)
