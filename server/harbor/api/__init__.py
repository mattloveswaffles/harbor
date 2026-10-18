"""API routers. Every endpoint lives under /api/v1 (except /health)."""

from fastapi import APIRouter

from harbor.api import (
    advisor,
    auth,
    chat,
    connections,
    demo,
    evacuation,
    events,
    health,
    plan,
    portfolio,
    profile,
    sensors,
    storm,
    users,
    weather,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(profile.router)
router.include_router(connections.router)
router.include_router(storm.router)
router.include_router(weather.router)
router.include_router(sensors.router)
router.include_router(evacuation.router)
router.include_router(plan.router)
router.include_router(advisor.router)
router.include_router(portfolio.router)
router.include_router(events.router)
router.include_router(chat.router)
router.include_router(demo.router)

health_router = health.router
