from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.api.schemas import DashboardSummary
from rag_platform.application.db.models import (
    ChatMessage,
    Document,
    DriveSyncState,
    IngestionJob,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/dashboard", response_model=DashboardSummary)
async def dashboard(
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
) -> DashboardSummary:
    session = request.state.db
    tenant = Document.tenant_id == context.tenant_id
    total = await session.scalar(select(func.count(Document.id)).where(tenant)) or 0
    indexed = (
        await session.scalar(
            select(func.count(Document.id)).where(tenant, Document.status == "ACTIVE")
        )
        or 0
    )
    failed = (
        await session.scalar(
            select(func.count(Document.id)).where(tenant, Document.status.like("FAILED%"))
        )
        or 0
    )
    since = datetime.now(UTC) - timedelta(days=7)
    queries = (
        await session.scalar(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.tenant_id == context.tenant_id,
                ChatMessage.role == "user",
                ChatMessage.created_at >= since,
            )
        )
        or 0
    )
    uploads = (
        await session.scalar(
            select(func.count(IngestionJob.id)).where(
                IngestionJob.tenant_id == context.tenant_id,
                IngestionJob.created_at >= since,
            )
        )
        or 0
    )
    drive_status = (
        await session.scalar(
            select(DriveSyncState.status)
            .where(DriveSyncState.tenant_id == context.tenant_id)
            .limit(1)
        )
        or "NOT_CONFIGURED"
    )
    return DashboardSummary(
        total_documents=total,
        indexed_documents=indexed,
        failed_documents=failed,
        recent_queries=queries,
        recent_uploads=uploads,
        drive_sync_status=drive_status,
        system_status="READY",
    )
