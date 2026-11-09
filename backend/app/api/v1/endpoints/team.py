from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.core.cache import cache_manager
from app.core.config import settings
from app.core.database import get_db_session
from app.domain.booking.models import Booking, BookingStatus, FieldAgent
from app.domain.user.models import User, UserRole

router = APIRouter()

_LOCATION_TTL = 300  # 5 min — stale after this → agent is "offline"


class LocationUpdate(BaseModel):
    lat: float
    lng: float
    heading: float = 0
    status: str = "busy"


@router.get("/team")
async def list_team(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Return all field agents for the current tenant with live telemetry from Redis."""
    result = await session.execute(select(FieldAgent).where(FieldAgent.tenant_id == current_user.tenant_id))
    agents = result.scalars().all()

    team = []
    for index, agent in enumerate(agents):
        # Fetch live location from Redis (set by PATCH /team/{id}/location)
        live = await cache_manager.get(f"team_location:{agent.id}")

        if live:
            live_status = {
                "status": live.get("status", "busy"),
                "currentJobId": live.get("currentJobId"),
                "lastPing": live.get("lastPing", datetime.now(timezone.utc).isoformat()),
                "lat": live.get("lat", 0),
                "lng": live.get("lng", 0),
                "heading": live.get("heading", 0),
                "speed": live.get("speed", 0),
            }
        elif settings.DEMO_MODE:
            # Redis is deliberately disabled for the synthetic demo. Stable London
            # telemetry keeps the real endpoint and map useful without a cache service.
            demo_locations = ((51.5010, -0.1416), (51.5034, -0.1276), (51.5202, -0.0977))
            lat, lng = demo_locations[index % len(demo_locations)]
            live_status = {
                "status": "available",
                "currentJobId": None,
                "lastPing": datetime.now(timezone.utc).isoformat(),
                "lat": lat,
                "lng": lng,
                "heading": 0,
                "speed": 0,
            }
        else:
            live_status = {
                "status": "offline",
                "currentJobId": None,
                "lastPing": (
                    agent.last_location_update.isoformat()
                    if agent.last_location_update
                    else datetime.now(timezone.utc).isoformat()
                ),
                "lat": 0,
                "lng": 0,
                "heading": 0,
                "speed": 0,
            }

        user = agent.user
        team.append(
            {
                "id": str(agent.id),
                # Lets a logged-in field_agent resolve "which team entry is me" (their
                # own FieldAgent.id, needed for the GPS-broadcast PATCH) without a
                # dedicated /team/me endpoint.
                "userId": str(agent.user_id),
                "fullName": f"{user.first_name} {user.last_name}".strip() if user else "Unknown",
                "avatar": (
                    f"https://ui-avatars.com/api/?name={user.first_name}+{user.last_name}&background=6366f1&color=fff"
                    if user and not settings.DEMO_MODE
                    else ""
                ),
                "role": "technician",
                "status": "active" if agent.is_active else "inactive",
                "liveStatus": live_status,
            }
        )

    return team


@router.patch("/team/{agent_id}/location")
async def update_agent_location(
    agent_id: UUID,
    payload: LocationUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Store an agent's GPS update in Redis and update its database timestamp.
    Only the agent's user account or an administrator may update the position."""
    agent = (
        await session.execute(
            select(FieldAgent).where(FieldAgent.id == agent_id, FieldAgent.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if current_user.role != UserRole.ADMIN and agent.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot update another agent's location")

    now = datetime.now(timezone.utc)

    
    await cache_manager.set(
        f"team_location:{agent_id}",
        {
            "lat": payload.lat,
            "lng": payload.lng,
            "heading": payload.heading,
            "status": payload.status,
            "speed": 0,
            "lastPing": now.isoformat(),
            "currentJobId": None,
        },
        ttl=_LOCATION_TTL,
    )

    # Update DB timestamp (no PostGIS write to avoid adding a migration dep here)
    agent.last_location_update = now
    await session.commit()

    return {"status": "ok"}


@router.get("/routes/{agent_id}")
async def get_agent_route(
    agent_id: UUID, session: AsyncSession = Depends(get_db_session), current_user: User = Depends(get_current_user)
):
    """Return the active route for an agent, derived from their assigned bookings."""
    # Fetch the agent's active booking to build a simple two-point route. Tenant-filtered:
    # without it any authenticated caller could probe another tenant's booking ids.
    result = await session.execute(
        select(Booking)
        .where(
            Booking.field_agent_id == agent_id,
            Booking.tenant_id == current_user.tenant_id,
            Booking.status.in_([BookingStatus.ASSIGNED, BookingStatus.IN_PROGRESS]),
        )
        .limit(1)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="No active route for agent")

    # Live coords from Redis (or default London coords as fallback)
    live = await cache_manager.get(f"team_location:{agent_id}")
    origin = [live["lng"], live["lat"]] if live else [-0.1278, 51.5074]

    return {
        "techId": str(agent_id),
        "jobId": str(booking.id),
        "geometry": {
            "type": "LineString",
            "coordinates": [origin],  # Single-point until OR-Tools wired (B7)
        },
        "duration": 600,
        "distance": 0,
        "status": "normal",
    }
