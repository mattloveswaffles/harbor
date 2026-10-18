"""FastAPI app: wiring, CORS, the error envelope, the clock header, the bank, the scheduler and the website."""

import threading
from contextlib import asynccontextmanager
from pathlib import PurePath

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from harbor.api import health, router
from harbor.auth import LoginLimiter
from harbor.bank import Bank, NessieConfigError, NessieError, NessieRejected, make_bank
from harbor.clock import Clock, DemoClock, RealClock, iso
from harbor.config import Settings, get_settings
from harbor.db import init_db, make_engine
from harbor.errors import HarborError, error_body
from harbor.ticker import start_scheduler


class Site(StaticFiles):
    """The built React app: extensionless paths serve index.html; unknown /api paths stay 404s."""

    def lookup_path(self, path: str):
        found = super().lookup_path(path)
        route = PurePath(path)  # OS separators
        if found[1] is None and not route.suffix and route.parts[:1] != ("api",):
            return super().lookup_path("index.html")
        return found


def create_app(settings: Settings | None = None, *, clock: Clock | None = None, bank: Bank | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings, clock and bank."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = start_scheduler(app) if settings.scheduler_enabled else None
        try:
            yield
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)
            await app.state.bank.close()

    app = FastAPI(title="Harbor API", version="1.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = clock or (
        DemoClock(settings.demo_start, settings.demo_speed, idle=RealClock().now)
        if settings.harbor_mode == "demo"
        else RealClock()
    )
    app.state.bank = bank or make_bank(settings)
    app.state.engine = make_engine(settings.database_url)
    init_db(app.state.engine)
    app.state.login_limiter = LoginLimiter()
    app.state.nessie_check = None  # (checked at, status): see api/health.py
    app.state.tick_lock = threading.Lock()
    app.state.tick_cursor = None  # how far the scheduler has caught up (storm time)
    app.state.llm_model = None  # made on first use (harbor.ai.llm.model)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Server-Time"],
    )
    app.include_router(router)
    app.include_router(health.router)

    @app.middleware("http")
    async def add_server_time(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Server-Time"] = iso(app.state.clock.now())  # the demo clock follows the replay
        return response

    @app.exception_handler(HarborError)
    async def harbor_error(request: Request, exc: HarborError):
        return JSONResponse(error_body(exc.code, exc.message, exc.fields), status_code=exc.status)

    @app.exception_handler(NessieError)
    async def bank_error(request: Request, exc: NessieError):
        if isinstance(exc, NessieConfigError):
            status, code = 503, "bank_not_configured"
        elif isinstance(exc, NessieRejected):
            status, code = 502, "bank_rejected"
        else:
            status, code = 503, "bank_unavailable"
        return JSONResponse(error_body(code, f"Nessie: {exc.message}"), status_code=status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        # Routes can raise HTTPException(status, detail={"code": ..., "message": ...}).
        if isinstance(exc.detail, dict):
            body = error_body(exc.detail.get("code", f"http_{exc.status_code}"), exc.detail.get("message", ""))
        else:
            body = error_body(f"http_{exc.status_code}", str(exc.detail))
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(error_body("validation_error", "Some fields are invalid.", fields), status_code=422)

    # Last, so the API routes above always win
    if settings.site_dir.is_dir():
        app.mount("/", Site(directory=settings.site_dir, html=True), name="site")

    return app


app = create_app()
