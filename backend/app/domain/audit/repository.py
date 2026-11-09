from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import get_current_tenant
from app.domain.audit.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        action: str,
        entity_type: str,
        entity_id: Optional[UUID] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """Create audit log entry"""
        tenant_id = get_current_tenant()
        if not tenant_id:
            raise ValueError("Tenant context required")

        audit_log = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.session.add(audit_log)
        await self.session.flush()
        return audit_log

    async def get_by_entity(self, entity_type: str, entity_id: UUID, limit: int = 50) -> List[AuditLog]:
        """Get audit logs for specific entity"""
        tenant_id = get_current_tenant()
        query = (
            select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )

        if tenant_id:
            query = query.where(AuditLog.tenant_id == tenant_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_user(self, user_id: UUID, limit: int = 100) -> List[AuditLog]:
        """Get audit logs for specific user"""
        tenant_id = get_current_tenant()
        query = select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.created_at.desc()).limit(limit)

        if tenant_id:
            query = query.where(AuditLog.tenant_id == tenant_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())
