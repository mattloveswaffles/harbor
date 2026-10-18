"""GET /health. nessie=ok means the demo customer was found (a wrong key returns an empty bank, not an error)."""

import time

from fastapi import APIRouter, Request

from harbor.ai.llm import ai_enabled
from harbor.bank import NessieError
from harbor.clock import iso
from harbor.deps import BankDep, ClockDep, SessionDep, SettingsDep
from harbor.schemas import HealthOut

router = APIRouter(tags=["health"])

NESSIE_CHECK_TTL_S = 30  # real seconds; health is polled, Nessie is slow


async def nessie_status(request: Request, session, bank, settings) -> str:
    if not settings.nessie_api_key.get_secret_value():
        return "missing_key"
    cached = getattr(request.app.state, "nessie_check", None)
    if cached and time.monotonic() - cached[0] < NESSIE_CHECK_TTL_S:
        return cached[1]
    try:
        await bank.list_customers()
        status = "ok"
    except NessieError:
        status = "degraded"
    request.app.state.nessie_check = (time.monotonic(), status)
    return status


@router.get("/health", response_model=HealthOut)
async def health(request: Request, session: SessionDep, bank: BankDep, clock: ClockDep, settings: SettingsDep) -> dict:
    return {
        "ok": True,
        "mode": settings.harbor_mode,
        "nessie": await nessie_status(request, session, bank, settings),
        "nhc": "replay" if settings.harbor_mode == "demo" else "unchecked",
        "ai": "ok" if ai_enabled(request.app) else "off",
        "chat": "ok" if ai_enabled(request.app) else "off",
        "clock": iso(clock.now()),
    }
