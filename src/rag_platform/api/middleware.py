from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("rag_platform.api")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        header = request.app.state.settings.api.request_id_header
        request_id = request.headers.get(header) or f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers[header] = request_id
        logger.info(
            "request_complete method=%s path=%s status=%s request_id=%s latency_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            (time.perf_counter() - started) * 1000,
        )
        return response


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
