"""Cache immutable query shapes, never tenant data, identities, or response rows."""

from functools import lru_cache

from sqlalchemy import DateTime, Integer, bindparam, func, select
from sqlalchemy.orm import aliased, noload

from app.domain.booking.models import Booking, BookingStatus, FieldAgent, Service
from app.domain.booking.schemas import BookingRead
from app.domain.user.models import User

CAPACITY_STATES = (
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.ASSIGNED,
    BookingStatus.ON_MY_WAY,
    BookingStatus.ARRIVED,
    BookingStatus.DELAYED,
    BookingStatus.IN_PROGRESS,
)


@lru_cache(maxsize=4)
def booking_statement(tenant_scoped: bool, relationships: bool):
    query = select(Booking).where(Booking.id == bindparam("booking_id"))
    if tenant_scoped:
        query = query.where(Booking.tenant_id == bindparam("tenant_id"))
    if not relationships:
        query = query.options(noload("*"))
    return query


@lru_cache(maxsize=4)
def availability_statement(tenant_scoped: bool, exclude: bool):
    query = (
        select(Booking.id)
        .where(
            Booking.provider_id == bindparam("provider_id"),
            Booking.status.in_(CAPACITY_STATES),
            func.booking_time_range(Booking.scheduled_time, Booking.duration_minutes).op("&&")(
                func.booking_time_range(
                    bindparam("scheduled_time", type_=DateTime(timezone=True)), bindparam("duration_minutes", type_=Integer)
                )
            ),
        )
        .limit(1)
    )
    if tenant_scoped:
        query = query.where(Booking.tenant_id == bindparam("tenant_id"))
    if exclude:
        query = query.where(Booking.id != bindparam("exclude_id"))
    return query


@lru_cache(maxsize=32)
def enriched_statement(filters: tuple[str, ...], status: bool, tenant_scoped: bool):
    agent_user = aliased(User)
    customer_name = func.nullif(func.trim(func.concat(User.first_name, " ", User.last_name)), "")
    agent_name = func.nullif(func.trim(func.concat(agent_user.first_name, " ", agent_user.last_name)), "")
    query = (
        select(
            *[getattr(Booking, name).label(name) for name in BookingRead.model_fields],
            customer_name.label("customer_name"),
            User.phone.label("customer_phone"),
            Service.name.label("service_name"),
            Service.service_type.label("service_type"),
            FieldAgent.id.label("assigned_agent_id"),
            agent_name.label("assigned_agent_name"),
        )
        .select_from(Booking)
        .outerjoin(User, Booking.customer_id == User.id)
        .outerjoin(Service, Booking.service_id == Service.id)
        .outerjoin(FieldAgent, Booking.field_agent_id == FieldAgent.id)
        .outerjoin(agent_user, FieldAgent.user_id == agent_user.id)
    )
    if tenant_scoped:
        query = query.where(Booking.tenant_id == bindparam("tenant_id"))
    if status:
        query = query.where(Booking.status == bindparam("booking_status"))
    for field in filters:
        query = query.where(getattr(Booking, field) == bindparam(field))
    return (
        query.order_by(Booking.scheduled_time.desc())
        .offset(bindparam("skip", type_=Integer))
        .limit(bindparam("limit", type_=Integer))
    )
