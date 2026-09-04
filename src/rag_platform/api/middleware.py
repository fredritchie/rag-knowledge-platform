from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from rag_platform.observability import (
    HTTP_DURATION,
    HTTP_REQUESTS,
    reset_request_id,
    reset_tenant_id,
    service_var,
    set_request_id,
    set_tenant_id,
    tracer,
)

logger = logging.getLogger("rag_platform.api")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        header = request.app.state.settings.api.request_id_header
        request_id = request.headers.get(header) or f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id
        request.state.tenant_id = None
        request_token = set_request_id(request_id)
        tenant_token = set_tenant_id(None)
        started = time.perf_counter()
        with tracer("rag-platform.api").start_as_current_span("rag.request") as span:
            span.set_attribute("http.request.method", request.method)
            span.set_attribute("rag.request_id", request_id)
            try:
                response = await call_next(request)
                response.headers[header] = request_id
                route = getattr(request.scope.get("route"), "path", "unmatched")
                status = str(response.status_code)
                elapsed = time.perf_counter() - started
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", response.status_code)
                span.set_attribute("rag.tenant_id", request.state.tenant_id or "unknown")
                HTTP_REQUESTS.labels(service_var.get(), request.method, route, status).inc()
                HTTP_DURATION.labels(service_var.get(), request.method, route).observe(elapsed)
                logger.info(
                    "request_complete",
                    extra={
                        "operation": f"{request.method} {route}",
                        "status": status,
                        "latency_ms": round(elapsed * 1000, 2),
                        "tenant_id": request.state.tenant_id,
                    },
                )
                return response
            finally:
                reset_tenant_id(tenant_token)
                reset_request_id(request_token)


class InMemoryRateLimiter:
    def __init__(self, requests: int, window_seconds: int):
        self.requests = requests
        self.window_seconds = window_seconds
        self.entries: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        queue = self.entries[key]
        while queue and queue[0] <= now - self.window_seconds:
            queue.popleft()
        remaining = max(0, self.requests - len(queue))
        if len(queue) >= self.requests:
            return False, 0
        queue.append(now)
        return True, remaining - 1


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = request.app.state.settings.api
        if not settings.rate_limit_enabled or request.url.path in {"/live", "/ready"}:
            return await call_next(request)
        key = request.client.host if request.client else "unknown"
        allowed, remaining = request.app.state.rate_limiter.check(key)
        if not allowed:
            request_id = getattr(request.state, "request_id", "unknown")
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMITED",
                    "message": "Rate limit exceeded",
                    "request_id": request_id,
                    "details": {},
                },
                headers={"Retry-After": str(settings.rate_limit_window_seconds)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


class DatabaseSessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        async with request.app.state.database.sessions() as session:
            request.state.db = session
            try:
                response = await call_next(request)
                if response.status_code >= 400:
                    await session.rollback()
                else:
                    await session.commit()
                return response
            except Exception:
                await session.rollback()
                raise
