from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.application.db.models import AuditEvent

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/events")
async def audit_events(
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: str | None = None,
) -> list[dict]:
    filters = [AuditEvent.tenant_id == context.tenant_id]
    if action:
        filters.append(AuditEvent.action == action)
    rows = await request.state.db.scalars(
        select(AuditEvent)
        .where(*filters)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": row.id,
            "request_id": row.request_id,
            "user_id": row.user_id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "outcome": row.outcome,
            "details": row.details,
            "created_at": row.created_at,
        }
        for row in rows.all()
    ]
