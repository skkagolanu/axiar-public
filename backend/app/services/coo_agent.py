"""Tenant-scoped tool-calling business assistant using LangChain and Ollama.
The bounded tool loop retrieves business data and synthesizes an answer;
when model access is unavailable, the service returns the retrieved data."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenant_context import get_current_tenant
from app.domain.analytics.demand_forecast import DemandForecastService
from app.domain.booking.models import Booking, BookingStatus

logger = logging.getLogger(__name__)

try:
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import tool
    from langchain_ollama import ChatOllama

    LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when AI extras are absent
    logger.warning("LangChain not available; Virtual COO will run in data-only fallback mode")
    LANGCHAIN_AVAILABLE = False


# Tool *schemas* shown to the LLM. Execution is dispatched to COOAgent's tenant-scoped
# methods (these stubs are never invoked directly), so the LLM sees the interface while
if LANGCHAIN_AVAILABLE:

    @tool
    def revenue_summary(days: int = 30) -> str:
        """Revenue and completed-booking value over the last N days (default 30)."""
        raise NotImplementedError

    @tool
    def booking_stats(days: int = 30) -> str:
        """Booking counts by status plus completion/cancellation rates over the last N days."""
        raise NotImplementedError

    @tool
    def demand_forecast(days_ahead: int = 14) -> str:
        """Predicted booking demand for the upcoming N days (default 14)."""
        raise NotImplementedError

    @tool
    def peak_hours() -> str:
        """The busiest hours of the day by booking volume."""
        raise NotImplementedError

    _TOOL_SCHEMAS = [revenue_summary, booking_stats, demand_forecast, peak_hours]
else:
    _TOOL_SCHEMAS = []


def _enum_value(v: Any) -> Any:
    return getattr(v, "value", v)


class COOAgent:
    """LangChain tool-calling 'Virtual COO' over the business's real data."""

    MAX_STEPS = 4
    _ALLOWED_ARGS = {
        "revenue_summary": ["days"],
        "booking_stats": ["days"],
        "demand_forecast": ["days_ahead"],
        "peak_hours": [],
    }

    def __init__(self, session: AsyncSession):
        self.session = session
        self.model = settings.AI_MODEL
        self.base_llm = None
        self.llm = None
        if LANGCHAIN_AVAILABLE:
            try:
                # convention) -- client_kwargs is threaded through to the underlying
                # ollama.Client/AsyncClient, which passes it to httpx. Without this,
                # a hung Ollama process could block a request indefinitely instead
                # of failing after a bounded wait.
                self.base_llm = ChatOllama(
                    model=self.model,
                    base_url=settings.OLLAMA_BASE_URL,
                    temperature=0.3,
                    client_kwargs={"timeout": 30.0},
                )
                self.llm = self.base_llm.bind_tools(_TOOL_SCHEMAS)
            except Exception as exc:  # pragma: no cover - construction rarely fails
                logger.warning("ChatOllama init failed (%s); using data-only fallback", exc)
                self.base_llm = self.llm = None

    # ------------------------------------------------------------------ tools
    def _tenant_filter(self, query):
        tenant_id = get_current_tenant()
        if tenant_id:
            return query.where(Booking.tenant_id == tenant_id)
        return query

    async def _revenue_summary(self, days: int = 30) -> dict:
        days = max(1, min(int(days), 365))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = select(
            func.count(Booking.id),
            func.coalesce(func.sum(Booking.total_paid_cents), 0),
            func.coalesce(func.sum(Booking.base_price_cents), 0),
        ).where(and_(Booking.status == BookingStatus.COMPLETED, Booking.completed_at >= cutoff))
        count, paid_cents, value_cents = (await self.session.execute(self._tenant_filter(query))).one()
        count = int(count or 0)
        avg = (value_cents / count / 100) if count else 0
        return {
            "period_days": days,
            "completed_bookings": count,
            "revenue_collected_gbp": round((paid_cents or 0) / 100, 2),
            "booked_value_gbp": round((value_cents or 0) / 100, 2),
            "avg_booking_value_gbp": round(avg, 2),
        }

    async def _booking_stats(self, days: int = 30) -> dict:
        days = max(1, min(int(days), 365))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = select(Booking.status, func.count(Booking.id)).where(Booking.scheduled_time >= cutoff).group_by(Booking.status)
        rows = (await self.session.execute(self._tenant_filter(query))).all()
        by_status = {_enum_value(status): int(c) for status, c in rows}
        total = sum(by_status.values())
        completed = by_status.get("completed", 0)
        cancelled = by_status.get("cancelled", 0)
        return {
            "period_days": days,
            "total_bookings": total,
            "by_status": by_status,
            "completion_rate_pct": round(completed / total * 100, 1) if total else 0,
            "cancellation_rate_pct": round(cancelled / total * 100, 1) if total else 0,
        }

    async def _demand_forecast(self, days_ahead: int = 14) -> dict:
        days_ahead = max(1, min(int(days_ahead), 90))
        forecasts = await DemandForecastService(self.session).forecast_demand(days_ahead)
        total = sum(f.get("predicted_bookings", 0) for f in forecasts)
        return {"days_ahead": days_ahead, "predicted_total_bookings": total, "daily": forecasts[:14]}

    async def _peak_hours(self) -> dict:
        hours = await DemandForecastService(self.session).get_peak_hours()
        top = sorted(hours.items(), key=lambda kv: kv[1], reverse=True)[:5]
        return {"top_hours": [{"hour": h, "share_pct": round(pct, 1)} for h, pct in top]}

    # ------------------------------------------------------------------ dispatch
    def _safe_args(self, name: str, args: dict) -> dict:
        """Keep only known integer args; ignore hallucinated keys/values."""
        out: dict[str, int] = {}
        for key in self._ALLOWED_ARGS.get(name, []):
            if key in (args or {}):
                try:
                    out[key] = int(args[key])
                except (TypeError, ValueError):
                    pass
        return out

    async def _dispatch(self, name: str, args: dict) -> dict:
        runner = {
            "revenue_summary": self._revenue_summary,
            "booking_stats": self._booking_stats,
            "demand_forecast": self._demand_forecast,
            "peak_hours": self._peak_hours,
        }.get(name)
        if runner is None:
            return {"error": f"unknown tool '{name}'"}
        try:
            return await runner(**self._safe_args(name, args))
        except Exception as exc:
            logger.error("COO tool %s failed: %s", name, exc)
            return {"error": "tool failed"}

    # ------------------------------------------------------------------ entry
    def _system_prompt(self) -> str:
        today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
        return (
            "You are Axiar's Virtual COO, a concise, data-driven advisor for a service business. "
            f"Today is {today}. Use the available tools to fetch real figures before answering; "
            "never invent numbers. Amounts are in GBP. Answer in 2-5 sentences, action-oriented."
        )

    async def ask(self, question: str) -> dict:
        """Answer a business question via the LangChain tool-calling loop, or fall back to data."""
        if self.llm is None:
            return await self._fallback()
        try:
            return await self._run_agent(question)
        except Exception as exc:
            logger.error("COO agent run failed: %s", exc)
            return await self._fallback()

    async def _run_agent(self, question: str) -> dict:
        messages: list = [SystemMessage(content=self._system_prompt()), HumanMessage(content=question)]
        data: dict[str, Any] = {}
        used: list[str] = []

        for _ in range(self.MAX_STEPS):
            ai = await self.llm.ainvoke(messages)
            messages.append(ai)
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                return {"answer": (ai.content or "").strip(), "tools_used": used, "data": data}
            for call in tool_calls:
                name = call.get("name")
                result = await self._dispatch(name, call.get("args") or {})
                data[name] = result
                used.append(name)
                messages.append(ToolMessage(content=json.dumps(result, default=str), tool_call_id=call.get("id", name)))

        # Out of steps: force a final answer from the gathered data (no more tools).
        final = await self.base_llm.ainvoke(messages + [HumanMessage(content="Give your final concise answer now.")])
        return {"answer": (final.content or "").strip(), "tools_used": used, "data": data}

    async def _fallback(self) -> dict:
        """No LLM available: return the core business data directly so the user still gets value."""
        data: dict[str, Any] = {}
        used: list[str] = []
        for name in ("revenue_summary", "booking_stats"):
            data[name] = await self._dispatch(name, {})
            used.append(name)
        return {
            "answer": "The AI summariser is unavailable right now, so here is your latest data directly.",
            "tools_used": used,
            "data": data,
        }
