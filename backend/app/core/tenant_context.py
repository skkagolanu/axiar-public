import uuid
from contextvars import ContextVar


tenant_context: ContextVar[uuid.UUID | None] = ContextVar("tenant_context", default=None)


def get_current_tenant() -> uuid.UUID | None:
    """Get current tenant ID from context"""
    return tenant_context.get()


def set_current_tenant(tenant_id: uuid.UUID | None) -> None:
    """Set current tenant ID in context"""
    tenant_context.set(tenant_id)
