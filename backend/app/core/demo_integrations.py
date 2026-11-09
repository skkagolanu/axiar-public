"""Deterministic adapters for the hosted synthetic-data demo."""

from typing import Any


class DemoIntegrationAdapter:
    """Replace outbound third-party calls while preserving application workflows."""

    _POSTCODES = {
        "SW1A1AA": (51.5010, -0.1416),
        "SW1A2AA": (51.5034, -0.1276),
        "EC1A1BB": (51.5202, -0.0977),
    }

    def notification_result(self, channel: str, target: str) -> dict[str, str]:
        return {"status": "demo", "channel": channel, "target": target}

    def geocode_postcode(self, postcode: str) -> tuple[float, float] | None:
        return self._POSTCODES.get(postcode.replace(" ", "").upper())

    def ai_response(self, query: str, context: list[dict[str, Any]] | None = None) -> str:
        prefix = "Based on Axiar's synthetic demo data"
        if context:
            return f"{prefix}, review the highlighted operational context before assigning the next job."
        if "schedule" in query.lower() or "booking" in query.lower():
            return f"{prefix}, prioritize confirmed bookings, then assign the nearest available field agent."
        return f"{prefix}, focus on today's bookings, team availability, and outstanding customer follow-ups."


demo_integrations = DemoIntegrationAdapter()
