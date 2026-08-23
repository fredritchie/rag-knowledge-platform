from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rag_platform.api.auth import CognitoJWTVerifier
from rag_platform.api.errors import ApplicationError
from rag_platform.api.middleware import (
    DatabaseSessionMiddleware,
    InMemoryRateLimiter,
    RateLimitMiddleware,
    RequestContextMiddleware,
)
from rag_platform.api.routers import (
    admin,
    audit,
    auth,
    chat,
    documents,
    generation,
    health,
    ingestion,
    integrations,
    retrieval,
    tenants,
    users,
)
from rag_platform.api.storage import S3Storage
from rag_platform.application.db.session import Database
from rag_platform.config import Settings, load_settings
from rag_platform.generation.service import GenerationService
from rag_platform.retrieval.service import RetrievalService


def create_application(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    storage: Any | None = None,
    event_queue: Any | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    database = database or Database(settings.database)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await app.state.database.dispose()

    app = FastAPI(
        title=settings.api.title,
        version=settings.api.version,
        description=(
            "Tenant-scoped document ingestion, retrieval, grounded chat, administration, "
            "and audit API. Authenticate with an Amazon Cognito JWT."
        ),
        openapi_tags=[
            {"name": "health", "description": "Kubernetes liveness and readiness."},
            {"name": "auth", "description": "Current authenticated identity."},
            {"name": "tenants", "description": "Tenant profile."},
            {"name": "users", "description": "Tenant memberships and users."},
            {"name": "documents", "description": "Versioned S3-backed documents."},
            {"name": "ingestion", "description": "Asynchronous pipeline jobs."},
            {"name": "retrieval", "description": "ACL-filtered search."},
            {"name": "generation", "description": "Grounded answer generation."},
            {"name": "chat", "description": "Persistent conversations and traces."},
            {"name": "admin", "description": "Platform administration."},
            {"name": "audit", "description": "Tenant audit trail."},
            {"name": "integrations", "description": "Drive and queue administration."},
        ],
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.storage = storage or S3Storage(settings.storage)
    app.state.jwt_verifier = CognitoJWTVerifier(settings.auth)
    if (
        event_queue is None
        and settings.event_ingestion.enabled
        and settings.event_ingestion.dlq_url
    ):
        from rag_platform.workers.s3_events import SQSQueueClient

        event_queue = SQSQueueClient(settings)
    app.state.event_queue = event_queue
    app.state.rate_limiter = InMemoryRateLimiter(
        settings.api.rate_limit_requests, settings.api.rate_limit_window_seconds
    )
    retrieval_cache: dict[str, RetrievalService] = {}
    generation_cache: dict[str, GenerationService] = {}

    def get_retrieval(tenant_id: str) -> RetrievalService:
        if tenant_id not in retrieval_cache:
            tenant_settings = settings.model_copy(update={"tenant_id": tenant_id})
            retrieval_cache[tenant_id] = RetrievalService(tenant_settings)
        return retrieval_cache[tenant_id]

    def get_generation(tenant_id: str) -> GenerationService:
        if tenant_id not in generation_cache:
            tenant_settings = settings.model_copy(update={"tenant_id": tenant_id})
            generation_cache[tenant_id] = GenerationService(
                tenant_settings, retrieval=get_retrieval(tenant_id)
            )
        return generation_cache[tenant_id]

    app.state.get_retrieval = get_retrieval
    app.state.get_generation = get_generation

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", settings.api.request_id_header],
        expose_headers=[settings.api.request_id_header, "X-RateLimit-Remaining"],
    )
    app.add_middleware(DatabaseSessionMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", "unknown"),
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "request_id": getattr(request.state, "request_id", "unknown"),
                "details": {"errors": exc.errors()},
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected application error occurred",
                "request_id": getattr(request.state, "request_id", "unknown"),
                "details": {},
            },
        )

    for route in (
        health.router,
        auth.router,
        tenants.router,
        users.router,
        documents.router,
        ingestion.router,
        retrieval.router,
        generation.router,
        chat.router,
        admin.router,
        audit.router,
        integrations.router,
    ):
        app.include_router(route)
    return app
