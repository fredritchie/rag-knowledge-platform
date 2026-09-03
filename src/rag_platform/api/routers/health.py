from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from rag_platform.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/live", response_model=HealthResponse, summary="Process liveness")
async def live() -> HealthResponse:
    """Does not call external dependencies; a live process must not restart for their outage."""
    return HealthResponse(status="ok", checks={"process": "ok"})


@router.get("/ready", response_model=HealthResponse, summary="Dependency readiness")
async def ready(request: Request):
    settings = request.app.state.settings
    checks: dict[str, str] = {}
    if settings.health.check_database:
        try:
            await request.state.db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error:{type(exc).__name__}"
    async with httpx.AsyncClient(timeout=settings.health.timeout_seconds) as client:
        if settings.health.check_qdrant:
            try:
                response = await client.get(f"{settings.qdrant.url.rstrip('/')}/healthz")
                response.raise_for_status()
                checks["qdrant"] = "ok"
            except Exception as exc:
                checks["qdrant"] = f"error:{type(exc).__name__}"
        if settings.health.check_ollama:
            try:
                response = await client.get(f"{settings.generation.base_url.rstrip('/')}/api/tags")
                response.raise_for_status()
                checks["ollama"] = "ok"
            except Exception as exc:
                checks["ollama"] = f"error:{type(exc).__name__}"
    healthy = all(value == "ok" for value in checks.values())
    body = HealthResponse(status="ok" if healthy else "not_ready", checks=checks)
    return body if healthy else JSONResponse(status_code=503, content=body.model_dump())
