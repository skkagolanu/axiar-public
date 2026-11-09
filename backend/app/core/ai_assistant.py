import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.core.config import settings
from app.core.demo_integrations import demo_integrations
from app.core.vector_store import vector_store

logger = logging.getLogger(__name__)


class AIAssistant:
    """AI assistant with RAG capabilities"""

    def __init__(self) -> None:
        self.ollama_url = settings.OLLAMA_BASE_URL
        self.model = settings.AI_MODEL
        # paying the full 30s timeout on every call while it's down; a single
        # trial call after 30s decides whether to resume.
        self._breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=30.0)

    async def generate_response(
        self,
        query: str,
        context: Optional[List[Dict[str, Any]]] = None,
        tenant_id: Optional[str] = None,
    ) -> str:
        """Generate AI response with RAG context"""

        if settings.DEMO_MODE:
            return demo_integrations.ai_response(query, context)

        
        if not context:
            context = vector_store.search(query, n_results=3, tenant_id=tenant_id)

        
        context_text = "\n".join([doc["document"] for doc in context]) if context else ""

        prompt = f"""You are Axiar's AI assistant, helping service businesses optimize operations.

Context:
{context_text}

Question: {query}

Provide a helpful, concise answer based on the context above."""

        try:
            self._breaker.before_call()
        except CircuitOpenError:
            logger.warning("Ollama circuit breaker open — failing fast without calling")
            return "AI service temporarily unavailable."

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                    },
                )

                if response.status_code == 200:
                    result: Dict[str, Any] = response.json()
                    self._breaker.record_success()
                    return str(result.get("response", "I couldn't generate a response."))
                else:
                    logger.error(f"Ollama error: {response.status_code}")
                    self._breaker.record_failure()
                    return "AI service temporarily unavailable."

        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            self._breaker.record_failure()
            return "AI service temporarily unavailable."

    async def analyze_booking_patterns(self, tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze booking patterns for insights"""

        prompt = f"""Analyze these booking statistics and provide insights:
- Total bookings: {data.get('total_bookings', 0)}
- Completion rate: {data.get('completion_rate', 0)}%
- Average booking value: £{data.get('avg_value', 0)}
- Peak hours: {data.get('peak_hours', [])}

Provide 3 actionable recommendations."""

        response = await self.generate_response(prompt, tenant_id=tenant_id)

        return {
            "analysis": response,
            "metrics": data,
        }


ai_assistant = AIAssistant()
