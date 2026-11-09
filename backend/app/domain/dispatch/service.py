from typing import Dict, List, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.domain.booking.models import FieldAgent
from app.domain.dispatch.repository import DispatchRepository


class DispatchService:
    def __init__(self, dispatch_repo: DispatchRepository):
        self.dispatch_repo = dispatch_repo
        self.ollama_url = settings.OLLAMA_BASE_URL

    async def find_best_agent(
        self,
        latitude: float,
        longitude: float,
        service_type: str,
        required_skills: Optional[List[str]] = None,
    ) -> Optional[UUID]:
        """Find best field agent using AI scoring"""
        agents_with_distance = await self.dispatch_repo.find_available_agents(
            latitude=latitude,
            longitude=longitude,
            max_distance_km=50.0,
            required_skills=required_skills,
        )

        if not agents_with_distance:
            return None

        agent_scores = []
        for agent, distance_meters in agents_with_distance:
            workload = await self.dispatch_repo.get_agent_workload(agent.id)

            score_data = {
                "distance_km": round(distance_meters / 1000, 2),
                "rating": float(agent.average_rating),
                "workload": workload,
                "skills": agent.skills or [],
                "service_type": service_type,
            }

            ai_score = await self._get_ai_score(score_data)

            agent_scores.append(
                {
                    "agent_id": agent.id,
                    "distance_km": score_data["distance_km"],
                    "rating": score_data["rating"],
                    "workload": workload,
                    "ai_score": ai_score,
                }
            )

        if not agent_scores:
            return agents_with_distance[0][0].id

        best_agent = max(agent_scores, key=lambda x: x["ai_score"])
        return best_agent["agent_id"]

    async def _get_ai_score(self, agent_data: Dict) -> float:
        """Get AI-based score for agent selection"""
        prompt = f"""Score this field agent for job assignment (0-100):
Distance: {agent_data['distance_km']}km
Rating: {agent_data['rating']}/5.0
Current workload: {agent_data['workload']} active jobs
Skills: {', '.join(agent_data['skills'])}
Service type: {agent_data['service_type']}

Consider: proximity (40%), rating (30%), workload (20%), skill match (10%)
Return only a number between 0-100."""

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": "llama3.2",
                        "prompt": prompt,
                        "stream": False,
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    score_text = result.get("response", "50").strip()
                    try:
                        score = float(score_text.split()[0])
                        return max(0, min(100, score))
                    except (ValueError, IndexError):
                        pass

        except Exception:
            pass

        distance_score = max(0, 100 - (agent_data["distance_km"] * 2))
        rating_score = (agent_data["rating"] / 5.0) * 100
        workload_score = max(0, 100 - (agent_data["workload"] * 20))

        return (distance_score * 0.4) + (rating_score * 0.3) + (workload_score * 0.3)

    async def assign_agent(self, booking_id: UUID, agent_id: UUID):
        """Assign agent to booking"""
        return await self.dispatch_repo.assign_agent_to_booking(booking_id, agent_id)
