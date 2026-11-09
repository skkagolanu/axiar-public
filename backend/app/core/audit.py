import logging
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_manager
from app.domain.audit.repository import AuditRepository

logger = logging.getLogger(__name__)


async def audit_log(
    action: str,
    entity_type: str,
    entity_id: Optional[Any] = None,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    user_id: Optional[Any] = None,
    request: Optional[Request] = None,
    session: Optional[AsyncSession] = None,
) -> None:
    """Create an audit log entry.

    If `session` is provided, the entry is written in the caller's transaction (atomic with
    the audited operation — no orphan audit rows if the caller later rolls back, and the
    audit is rolled back if the operation fails). Otherwise a standalone session is used.
    """
    try:
        ip_address = None
        user_agent = None
        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

        if session is not None:
            # Same transaction as the caller; the caller owns commit/rollback.
            await AuditRepository(session).create(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_values=old_values,
                new_values=new_values,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return

        async with db_manager.get_session() as own_session:
            await AuditRepository(own_session).create(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_values=old_values,
                new_values=new_values,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await own_session.commit()

    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
