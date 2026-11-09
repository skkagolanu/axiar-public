"""Field operations repository"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.field_ops.models import Expense, ExpenseStatus


class ExpenseRepository:
    """Repository for expense data access"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, expense_id: UUID) -> Optional[Expense]:
        """Get expense by ID"""
        query = select(Expense).where(Expense.id == expense_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_agent(self, agent_id: UUID) -> List[Expense]:
        """Get all expenses for a field agent"""
        query = select(Expense).where(Expense.field_agent_id == agent_id).order_by(Expense.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, expense: Expense) -> Expense:
        """Create new expense"""
        self.session.add(expense)
        await self.session.flush()
        await self.session.refresh(expense)
        return expense

    async def update_status(self, expense_id: UUID, status: ExpenseStatus) -> Optional[Expense]:
        """Update expense status"""
        expense = await self.get_by_id(expense_id)
        if expense:
            expense.status = status
            await self.session.flush()
            await self.session.refresh(expense)
        return expense
