from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.api.auth import RequestContext
from rag_platform.application.db.models import AuditEvent


def add_audit_event(
    session: AsyncSession,
    request: Request,
    context: RequestContext,
    *,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    outcome: str = "SUCCESS",
    details: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            request_id=request.state.request_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            ip_address=request.client.host if request.client else None,
            details=details or {},
        )
    )
