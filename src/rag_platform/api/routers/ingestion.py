from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.api.errors import NotFoundError
from rag_platform.application.db.models import IngestionEvent, IngestionJob

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("QUERY")),
) -> dict:
    job = await request.state.db.scalar(
        select(IngestionJob).where(
            IngestionJob.id == job_id, IngestionJob.tenant_id == context.tenant_id
        )
    )
    if job is None:
        raise NotFoundError("Ingestion job", job_id)
    events = list(
        (
            await request.state.db.scalars(
                select(IngestionEvent)
                .where(IngestionEvent.job_id == job.id)
                .order_by(IngestionEvent.created_at)
            )
        ).all()
    )
    return {
        "id": job.id,
        "document_id": job.document_id,
        "document_version_id": job.document_version_id,
        "status": job.status,
        "stage": job.stage,
        "progress_percent": job.progress_percent,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "events": [
            {
                "stage": event.stage,
                "status": event.status,
                "progress_percent": event.progress_percent,
                "message": event.message,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }
