"""Demo reset endpoint — hosted-demo housekeeping only.

``POST /api/v1/demo/reset`` wipes only the dedicated synthetic tenant's rows and
re-runs the demo seed, restoring the pristine published state. Auth is a shared-secret header
(``X-Demo-Reset-Token`` == ``settings.DEMO_RESET_TOKEN``) rather than a user
JWT so a dumb external cron (cron-job.org) can call it nightly — which doubles
as the keep-alive that stops Supabase's free tier pausing the database. The
route 404s when no token is configured, so it does not exist outside the demo
deployment.
"""

import hmac
import logging

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.core.database import Base, db_manager
from app.domain.tenant.models import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
async def reset_demo(x_demo_reset_token: str = Header(default="")) -> dict:
    configured = settings.DEMO_RESET_TOKEN
    if not configured:
        raise HTTPException(status_code=404, detail="Not found")
    if not hmac.compare_digest(x_demo_reset_token, configured):
        raise HTTPException(status_code=403, detail="Forbidden")

    engine = db_manager.engines["main"]
    async with engine.begin() as conn:
        tenant_id = (
            await conn.execute(select(Tenant.id).where(Tenant.slug == settings.DEMO_TENANT_SLUG))
        ).scalar_one_or_none()
        if tenant_id is None:
            raise HTTPException(status_code=404, detail="Demo tenant not found")

        payments = Base.metadata.tables["payments"]
        refunds = Base.metadata.tables["refunds"]
        await conn.execute(
            refunds.delete().where(refunds.c.payment_id.in_(select(payments.c.id).where(payments.c.tenant_id == tenant_id)))
        )
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in {"tenants", "refunds"} and "tenant_id" in table.c:
                await conn.execute(table.delete().where(table.c.tenant_id == tenant_id))

    from scripts.seed_demo import seed

    async with db_manager.get_session() as session:
        await seed(session)

    logger.info("Demo reset complete")
    return {"status": "reset"}
