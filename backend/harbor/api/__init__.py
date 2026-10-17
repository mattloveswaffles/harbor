"""API routers. Every endpoint in docs/API.md lives under /api/v1 (except /health)."""

from fastapi import APIRouter

from harbor.api import auth, demo, evacuation, events, health, plan, portfolio, sensors, storm, users

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(storm.router)
router.include_router(sensors.router)
router.include_router(evacuation.router)
router.include_router(plan.router)
router.include_router(portfolio.router)
router.include_router(events.router)
router.include_router(demo.router)

health_router = health.router
