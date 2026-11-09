from logging.config import fileConfig
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import asyncio
import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import Base
from app.domain.tenant.models import Tenant
from app.domain.user.models import User
from app.domain.booking.models import Booking, Provider, Service, FieldAgent
from app.domain.booking_rules.rules import BookingRule
from app.domain.payment.models import Payment, Refund
from app.domain.payment.schedule import PaymentSchedule
from app.domain.audit.models import AuditLog

# registered on Base.metadata -- target_metadata (used for both real autogenerate
# and `alembic check`) silently omitted them, and `alembic check` flagged every
# one of these real, migration-managed tables as "removed" (present in the DB,
# absent from metadata) the first time it actually ran in CI.
from app.domain.chat.models import ChatMessage
from app.domain.dispute.models import Dispute
from app.domain.field_ops.models import Expense
from app.domain.marketing.models import EmailCampaign
from app.domain.promo.models import PromoCode
from app.domain.referral.models import Referral
from app.domain.review.models import Review
from app.domain.settings.models import TenantSettings
from app.core.outbox import OutboxMessage

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Register all mapped models so Alembic compares the complete application schema.
    extension_owned_tables = {
        row[0]
        for row in connection.execute(
            text(
                """
                SELECT DISTINCT c.relname
                FROM pg_depend d
                JOIN pg_extension e ON d.refobjid = e.oid
                JOIN pg_class c ON d.objid = c.oid
                WHERE d.deptype = 'e' AND c.relkind IN ('r', 'v', 'm')
                """
            )
        )
    }
    # That SELECT auto-begins a transaction on this connection (SQLAlchemy 2.0
    
    # start a fresh one, so roll this read-only one back first -- otherwise the
    # two conflict and alembic raises "assert self._transaction is not None".
    connection.rollback()

    def include_object(object, name, type_, reflected, compare_to):
        """Exclude any table/view owned by a Postgres extension (PostGIS, tiger_geocoder, etc.)."""
        if type_ == "table" and name in extension_owned_tables:
            return False
        return True

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        include_schemas=False
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    if os.getenv("DATABASE_URL"):
        configuration["sqlalchemy.url"] = os.getenv("DATABASE_URL")
    
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
