from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from rag_platform.api.auth import CognitoJWTVerifier
from rag_platform.api.errors import ApplicationError
from rag_platform.api.middleware import (
    DatabaseSessionMiddleware,
    InMemoryRateLimiter,
    RateLimitMiddleware,
    RequestContextMiddleware,
)
from rag_platform.api.routers import audit, auth, tenants, users
from rag_platform.application.db.session import Database
from rag_platform.config import Settings, load_settings


def create_application(settings: Settings | None = None) -> FastAPI:
    """Build the Phase 7 API and initialize its shared application state."""

    config = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = config
        app.state.database = Database(config.database)
        app.state.jwt_verifier = CognitoJWTVerifier(config.auth)
        app.state.rate_limiter = InMemoryRateLimiter(
            config.api.rate_limit_requests,
            config.api.rate_limit_window_seconds,
        )
        try:
            yield
        finally:
            await app.state.database.dispose()

    app = FastAPI(
        title=config.api.title,
        version=config.api.version,
        lifespan=lifespan,
    )
    app.add_middleware(DatabaseSessionMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", "unknown"),
                "details": exc.details,
            },
        )

    @app.get("/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["health"])
    async def ready(request: Request) -> dict[str, str]:
        if request.app.state.settings.health.check_database:
            await request.state.db.execute(text("SELECT 1"))
        return {"status": "ready"}

    app.include_router(auth.router)
    app.include_router(tenants.router)
    app.include_router(users.router)
    app.include_router(audit.router)
    return app
