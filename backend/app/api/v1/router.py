from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    ai,
    ai_scheduling,
    analytics,
    auth,
    booking_rules,
    bookings,
    campaigns,
    chat,
    cqrs_bookings,
    customers,
    dashboard,
    demo,
    dispatch,
    disputes,
    expenses,
    health,
    ml_analytics,
    mobile,
    monitoring,
    oauth,
    payment_schedules,
    payments,
    promo,
    providers,
    push,
    qr,
    referrals,
    reports,
    reviews,
    schedule,
    system_settings,
    team,
    voice,
)
from app.core.metrics import get_metrics

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(health.router)
v1_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
v1_router.include_router(auth.router)
v1_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
v1_router.include_router(cqrs_bookings.router, prefix="/bookings", tags=["cqrs"])
v1_router.include_router(booking_rules.router, prefix="/bookings", tags=["booking-rules"])
v1_router.include_router(payments.router, prefix="/payments", tags=["payments"])
v1_router.include_router(payment_schedules.router, prefix="/payments", tags=["payment-schedules"])
v1_router.include_router(promo.router, prefix="/promo", tags=["promo"])
v1_router.include_router(dispatch.router, prefix="/dispatch", tags=["dispatch"])
v1_router.include_router(providers.router, prefix="/providers", tags=["providers"])
v1_router.include_router(chat.router, prefix="/chat", tags=["chat"])
v1_router.include_router(oauth.router, prefix="/oauth", tags=["oauth"])
v1_router.include_router(qr.router, prefix="/qr", tags=["qr"])
v1_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
v1_router.include_router(expenses.router, prefix="/expenses", tags=["expenses"])
v1_router.include_router(mobile.router, prefix="/mobile", tags=["mobile"])
v1_router.include_router(voice.router, prefix="/voice", tags=["voice"])
v1_router.include_router(ai.router)
v1_router.include_router(ai_scheduling.router)
v1_router.include_router(push.router)
v1_router.include_router(analytics.router, tags=["analytics"])
v1_router.include_router(admin.router, tags=["admin"])
v1_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
v1_router.include_router(schedule.router, tags=["schedule"])
v1_router.include_router(customers.router, tags=["customers"])
v1_router.include_router(reports.router, prefix="/reports", tags=["reports"])
v1_router.include_router(team.router, tags=["team"])
v1_router.include_router(referrals.router, prefix="/referrals", tags=["referrals"])
v1_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
v1_router.include_router(ml_analytics.router, prefix="/ml", tags=["ml-analytics"])
v1_router.include_router(disputes.router, prefix="/disputes", tags=["disputes"])
v1_router.include_router(system_settings.router, prefix="/settings", tags=["settings"])
v1_router.include_router(demo.router)  # 404s unless DEMO_RESET_TOKEN is configured (hosted demo only)

# Prometheus metrics endpoint
v1_router.add_api_route("/metrics", get_metrics, methods=["GET"], tags=["metrics"])
