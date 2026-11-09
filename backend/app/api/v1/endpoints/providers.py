from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Float, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role
from app.core.database import get_db_session
from app.domain.booking.models import Provider, Service
from app.domain.booking.schemas import (
    ProviderCreate,
    ProviderRead,
    ServiceCreate,
    ServiceRead,
)
from app.domain.provider.repository import ProviderRepository, ServiceRepository
from app.domain.user.models import User, UserRole

router = APIRouter()


class ProviderSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_name: str
    description: Optional[str]
    average_rating: float
    total_reviews: int
    service_radius_km: int
    distance_km: Optional[float]
    services: List[ServiceRead] = []


class ProviderSearchError(BaseModel):
    detail: str


@router.get("/search", response_model=List[ProviderSearchResult])
async def search_providers(
    lat: float = Query(..., ge=-90, le=90, description="Search origin latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Search origin longitude"),
    service_type: Optional[str] = Query(None, description="Filter by service type (e.g. 'Plumbing')"),
    radius_km: float = Query(50.0, ge=1, le=500),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    PostGIS KNN provider search ranked by distance from the given coordinates.
    Optionally filtered by service_type. Only returns active providers.
    """
    origin_wkt = f"SRID=4326;POINT({lng} {lat})"

    # Distance in km using PostGIS ST_Distance (geography = metres)
    distance_expr = func.ST_Distance(
        Provider.location,
        func.ST_GeogFromText(origin_wkt),
    ).label("distance_m")

    query = (
        select(Provider, distance_expr)
        .where(
            Provider.is_active == True,  # noqa: E712
            Provider.tenant_id == current_user.tenant_id,
            Provider.location.isnot(None),
            # Only include providers within radius (convert m → km)
            func.ST_DWithin(
                Provider.location,
                func.ST_GeogFromText(origin_wkt),
                radius_km * 1000,
            ),
        )
        .order_by(distance_expr)
        .limit(limit)
    )

    # If service_type filter, join to Service table
    if service_type:
        query = query.where(
            Provider.id.in_(
                select(Service.provider_id).where(
                    Service.service_type.ilike(f"%{service_type}%"),
                    Service.is_available == True,  # noqa: E712
                )
            )
        )

    result = await db.execute(query)
    rows = result.all()

    # Fetch services for matching providers in one query
    provider_ids = [row.Provider.id for row in rows]
    services_result = await db.execute(
        select(Service).where(Service.provider_id.in_(provider_ids), Service.is_available == True)  # noqa: E712
    )
    services_by_provider: dict = {}
    for svc in services_result.scalars().all():
        services_by_provider.setdefault(svc.provider_id, []).append(svc)

    return [
        ProviderSearchResult(
            id=row.Provider.id,
            business_name=row.Provider.business_name,
            description=row.Provider.description,
            average_rating=float(row.Provider.average_rating or 0),
            total_reviews=row.Provider.total_reviews or 0,
            service_radius_km=row.Provider.service_radius_km,
            distance_km=round(row.distance_m / 1000, 2) if row.distance_m else None,
            services=services_by_provider.get(row.Provider.id, []),
        )
        for row in rows
    ]


@router.get(
    "/search/by-postcode",
    response_model=List[ProviderSearchResult],
    responses={
        501: {
            "model": ProviderSearchError,
            "description": "Postcode geocoding is not configured",
        }
    },
)
async def search_providers_by_postcode(
    postcode: str = Query(
        ...,
        min_length=1,
        max_length=16,
        description="UK postcode to search from (requires Google Maps key for geocoding)",
    ),
    service_type: Optional[str] = Query(None),
    radius_km: float = Query(50.0, ge=1, le=500),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Search providers near a postcode. Geocodes via the Google Maps Geocoding API
    then delegates to the lat/lng search endpoint logic.
    Returns 501 when GOOGLE_MAPS_API_KEY is not configured.
    """
    from app.core.config import settings

    if settings.DEMO_MODE:
        from app.core.demo_integrations import demo_integrations

        location = demo_integrations.geocode_postcode(postcode)
        if not location:
            raise HTTPException(
                status_code=422,
                detail=f"Postcode '{postcode}' is not in the synthetic demo region",
            )
        return await search_providers(
            lat=location[0],
            lng=location[1],
            service_type=service_type,
            radius_km=radius_km,
            limit=limit,
            current_user=current_user,
            db=db,
        )

    if not settings.GOOGLE_MAPS_API_KEY or settings.GOOGLE_MAPS_API_KEY.startswith("mock"):
        raise HTTPException(
            status_code=501,
            detail="Postcode geocoding requires GOOGLE_MAPS_API_KEY. Use /providers/search?lat=&lng= directly.",
        )

    import httpx

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(url, params={"address": postcode, "key": settings.GOOGLE_MAPS_API_KEY})
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        raise HTTPException(status_code=422, detail=f"Could not geocode postcode '{postcode}'")

    loc = data["results"][0]["geometry"]["location"]
    return await search_providers(
        lat=loc["lat"],
        lng=loc["lng"],
        service_type=service_type,
        radius_km=radius_km,
        limit=limit,
        current_user=current_user,
        db=db,
    )


@router.post("/", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
async def create_provider(
    provider_data: ProviderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create provider profile"""
    repo = ProviderRepository(db)
    existing = await repo.get_by_user_id(current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Provider profile already exists")

    provider = await repo.create(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        business_name=provider_data.business_name,
        description=provider_data.description,
        business_phone=provider_data.business_phone,
        business_email=provider_data.business_email,
        website_url=provider_data.website_url,
        service_radius_km=provider_data.service_radius_km,
    )
    await db.commit()
    return provider


@router.get("/me", response_model=ProviderRead)
async def get_my_provider(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get current user's provider profile"""
    repo = ProviderRepository(db)
    provider = await repo.get_by_user_id(current_user.id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider profile not found")
    return provider


@router.get("/{provider_id}", response_model=ProviderRead)
async def get_provider(
    provider_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get provider by ID"""
    repo = ProviderRepository(db)
    provider = await repo.get_by_id(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.get("/", response_model=List[ProviderRead])
async def list_providers(db: AsyncSession = Depends(get_db_session)):
    """List active providers within the resolved tenant for the public booking picker."""
    repo = ProviderRepository(db)
    return await repo.list_active()


@router.post(
    "/{provider_id}/services",
    response_model=ServiceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_service(
    provider_id: UUID,
    service_data: ServiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create service for provider"""
    provider_repo = ProviderRepository(db)
    provider = await provider_repo.get_by_id(provider_id)

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")

    service_repo = ServiceRepository(db)
    service = await service_repo.create(
        provider_id=provider_id,
        tenant_id=current_user.tenant_id,
        name=service_data.name,
        description=service_data.description,
        service_type=service_data.service_type,
        base_price_cents=service_data.base_price_cents,
        duration_minutes=service_data.duration_minutes,
    )
    await db.commit()
    return service


@router.get("/{provider_id}/services", response_model=List[ServiceRead])
async def list_provider_services(provider_id: UUID, db: AsyncSession = Depends(get_db_session)):
    """List services for a provider in the public booking picker."""
    service_repo = ServiceRepository(db)
    return await service_repo.list_by_provider(provider_id)


@router.get("/services/{service_id}", response_model=ServiceRead)
async def get_service(
    service_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get service by ID"""
    service_repo = ServiceRepository(db)
    service = await service_repo.get_by_id(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Delete service"""
    service_repo = ServiceRepository(db)
    service = await service_repo.get_by_id(service_id)

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    provider_repo = ProviderRepository(db)
    provider = await provider_repo.get_by_id(service.provider_id)

    if provider.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")

    await service_repo.delete(service_id)
    await db.commit()
