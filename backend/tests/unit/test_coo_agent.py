"""Unit tests for the Virtual COO agent's dispatch/fallback/loop logic.

These avoid a live DB and a live Ollama on purpose: tool methods are stubbed and the
LLM is mocked, so the control flow is verified deterministically in CI. The real
tenant-scoped SQL aggregates are exercised via the /api/v1/ai/coo endpoint against a
populated database. Tests do not require LangChain to be importable (the loop test
skips when it is absent).
"""

import pytest

from app.services.coo_agent import COOAgent


def test_safe_args_filters_unknown_keys_and_coerces_ints():
    agent = COOAgent(session=None)
    assert agent._safe_args("revenue_summary", {"days": "45", "evil": "x"}) == {"days": 45}
    assert agent._safe_args("revenue_summary", {"days": "not-an-int"}) == {}
    assert agent._safe_args("peak_hours", {"anything": 1}) == {}


@pytest.mark.asyncio
async def test_dispatch_routes_sanitizes_and_handles_unknown(monkeypatch):
    agent = COOAgent(session=None)
    captured = {}

    async def fake_revenue(days=30):
        captured["days"] = days
        return {"completed_bookings": 5}

    monkeypatch.setattr(agent, "_revenue_summary", fake_revenue)

    out = await agent._dispatch("revenue_summary", {"days": "60", "junk": "x"})
    assert out == {"completed_bookings": 5}
    assert captured["days"] == 60  # coerced + sanitized

    unknown = await agent._dispatch("does_not_exist", {})
    assert "error" in unknown


@pytest.mark.asyncio
async def test_ask_falls_back_to_core_data_without_llm(monkeypatch):
    agent = COOAgent(session=None)
    agent.llm = None  # force the data-only fallback path

    async def fake_rev(days=30):
        return {"completed_bookings": 2}

    async def fake_stats(days=30):
        return {"total_bookings": 4}

    monkeypatch.setattr(agent, "_revenue_summary", fake_rev)
    monkeypatch.setattr(agent, "_booking_stats", fake_stats)

    result = await agent.ask("how are we doing?")

    assert set(result["tools_used"]) == {"revenue_summary", "booking_stats"}
    assert result["data"]["revenue_summary"]["completed_bookings"] == 2
    assert "unavailable" in result["answer"].lower()


@pytest.mark.asyncio
async def test_run_agent_tool_calling_loop(monkeypatch):
    pytest.importorskip("langchain_core")
    from langchain_core.messages import AIMessage

    agent = COOAgent(session=None)

    # Step 1: model requests a tool call. Step 2: model gives a final answer.
    steps = iter(
        [
            AIMessage(content="", tool_calls=[{"name": "revenue_summary", "args": {"days": 30}, "id": "t1"}]),
            AIMessage(content="Revenue is up this month."),
        ]
    )

    class FakeLLM:
        async def ainvoke(self, _messages):
            return next(steps)

    agent.llm = FakeLLM()
    agent.base_llm = FakeLLM()

    async def fake_rev(days=30):
        return {"completed_bookings": 7}

    monkeypatch.setattr(agent, "_revenue_summary", fake_rev)

    result = await agent.ask("how's revenue?")

    assert result["tools_used"] == ["revenue_summary"]
    assert result["data"]["revenue_summary"]["completed_bookings"] == 7
    assert result["answer"] == "Revenue is up this month."
