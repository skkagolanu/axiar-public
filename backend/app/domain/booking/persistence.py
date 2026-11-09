"""Atomic booking, audit and outbox statements with reusable bound query shapes."""

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import bindparam, exists, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, raiseload

from app.core.outbox import OutboxMessage
from app.domain.audit.models import AuditLog
from app.domain.booking.models import Booking

CREATE_FIELDS = (
    "id",
    "tenant_id",
    "customer_id",
    "provider_id",
    "service_id",
    "scheduled_time",
    "duration_minutes",
    "description",
    "status",
    "location_postcode",
    "location_address",
    "base_price_cents",
    "payment_timing",
    "deposit_percentage",
    "deposit_paid_cents",
    "total_paid_cents",
    "version",
    "discount_cents",
    "route_order",
)
AUDIT_FIELDS = ("id", "tenant_id", "user_id", "action", "entity_type", "entity_id", "old_values", "new_values", "created_at")
OUTBOX_FIELDS = (
    "id",
    "tenant_id",
    "aggregate_type",
    "aggregate_id",
    "event_type",
    "payload",
    "status",
    "attempts",
    "created_at",
)


def _bound(table, prefix, name):
    return bindparam(prefix + name, type_=table.c[name].type)


@lru_cache(maxsize=4)
def _statement(create: bool, has_event: bool):
    table = Booking.__table__
    if create:
        changed = insert(table).values(**{name: _bound(table, "booking_", name) for name in CREATE_FIELDS})
    else:
        changed = (
            update(table)
            .where(
                table.c.id == _bound(table, "booking_", "id"),
                table.c.tenant_id == _bound(table, "booking_", "tenant_id"),
                table.c.version == _bound(table, "booking_", "version"),
            )
            .values(
                status=_bound(table, "booking_", "status"),
                version=table.c.version + 1,
                completed_at=_bound(table, "booking_", "completed_at"),
                updated_at=func.now(),
            )
        )
    written = changed.returning(*table.c).cte("written_booking")
    audit_table = AuditLog.__table__
    audit_values = select(*[_bound(audit_table, "audit_", name) for name in AUDIT_FIELDS]).where(exists(select(written.c.id)))
    audit = insert(audit_table).from_select(AUDIT_FIELDS, audit_values).cte("written_audit")
    journal = [audit]
    if has_event:
        outbox_table = OutboxMessage.__table__
        outbox_values = select(*[_bound(outbox_table, "outbox_", name) for name in OUTBOX_FIELDS]).where(
            exists(select(written.c.id))
        )
        journal.append(insert(outbox_table).from_select(OUTBOX_FIELDS, outbox_values).cte("written_outbox"))
    entity = aliased(Booking, written)
    return select(entity).options(raiseload("*")).add_cte(*journal)


async def write_with_journal(
    session: AsyncSession,
    *,
    create: bool,
    values: dict[str, Any],
    action: str,
    old_values: dict[str, Any] | None,
    new_values: dict[str, Any],
    user_id: UUID | None = None,
    event_type: str | None = None,
    event_data: dict[str, Any] | None = None,
) -> Booking | None:
    """A version mismatch returns no row and writes neither audit nor event.

    The caller owns COMMIT/ROLLBACK; this never acknowledges or publishes a
    booking before its outer transaction is durable.
    """
    now = datetime.now(timezone.utc)
    params = {"booking_" + name: value for name, value in values.items()}
    audit = dict(
        id=uuid4(),
        tenant_id=values["tenant_id"],
        user_id=user_id,
        action=action,
        entity_type="booking",
        entity_id=values["id"],
        old_values=old_values,
        new_values=new_values,
        created_at=now,
    )
    params.update({"audit_" + name: value for name, value in audit.items()})
    if event_type:
        outbox = dict(
            id=uuid4(),
            tenant_id=values["tenant_id"],
            aggregate_type="booking",
            aggregate_id=values["id"],
            event_type=event_type,
            payload=event_data or {},
            status="pending",
            attempts=0,
            created_at=now,
        )
        params.update({"outbox_" + name: value for name, value in outbox.items()})
    result = await session.execute(_statement(create, bool(event_type)), params, execution_options={"populate_existing": True})
    return result.scalar_one_or_none()
