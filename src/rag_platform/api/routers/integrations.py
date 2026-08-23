from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from rag_platform.api.audit import add_audit_event
from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.api.errors import ConflictError, NotFoundError
from rag_platform.api.schemas import (
    DriveConnectionCreate,
    DriveConnectionOut,
    DriveErrorOut,
    QueueHealthOut,
)
from rag_platform.application.db.models import (
    DriveChangeEvent,
    DriveCheckpoint,
    DriveConnection,
    DriveSyncState,
    IngestionReceipt,
)

router = APIRouter(prefix="/api/v1/admin", tags=["integrations"])


async def _connection(request: Request, tenant_id: str, connection_id: str):
    connection = await request.state.db.scalar(
        select(DriveConnection).where(
            DriveConnection.id == connection_id,
            DriveConnection.tenant_id == tenant_id,
        )
    )
    if connection is None:
        raise NotFoundError("Drive connection", connection_id)
    return connection


def _out(connection: DriveConnection, checkpoint: DriveCheckpoint) -> DriveConnectionOut:
    return DriveConnectionOut(
        connection_id=connection.id,
        display_name=connection.display_name,
        status=connection.status,
        sync_status=checkpoint.status,
        last_change_token_present=checkpoint.last_change_token is not None,
        last_success_time=checkpoint.last_success_time,
        next_sync_at=checkpoint.next_sync_at,
        error_count=checkpoint.error_count or 0,
        last_error=checkpoint.last_error,
    )


@router.post("/drive/connections", response_model=DriveConnectionOut, status_code=201)
async def connect_drive(
    body: DriveConnectionCreate,
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
) -> DriveConnectionOut:
    connection = DriveConnection(
        tenant_id=context.tenant_id,
        display_name=body.display_name,
        secret_reference=body.credentials_reference,
        status="ACTIVE",
    )
    request.state.db.add(connection)
    await request.state.db.flush()
    legacy = DriveSyncState(
        connection_id=connection.id,
        tenant_id=context.tenant_id,
        status="PENDING",
    )
    checkpoint = DriveCheckpoint(
        connection_id=connection.id,
        tenant_id=context.tenant_id,
        credentials_reference=body.credentials_reference,
        status="PENDING",
        error_count=0,
        next_sync_at=datetime.now(UTC),
    )
    request.state.db.add_all([legacy, checkpoint])
    add_audit_event(
        request.state.db,
        request,
        context,
        action="drive.connected",
        resource_type="drive_connection",
        resource_id=connection.id,
        details={"display_name": body.display_name},
    )
    return _out(connection, checkpoint)


@router.get("/drive/connections", response_model=list[DriveConnectionOut])
async def list_drive_connections(
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
) -> list[DriveConnectionOut]:
    rows = await request.state.db.execute(
        select(DriveConnection, DriveCheckpoint)
        .join(DriveCheckpoint, DriveCheckpoint.connection_id == DriveConnection.id)
        .where(DriveConnection.tenant_id == context.tenant_id)
        .order_by(DriveConnection.created_at.desc())
    )
    return [_out(connection, checkpoint) for connection, checkpoint in rows.all()]


@router.post("/drive/connections/{connection_id}/force-sync", status_code=202)
async def force_sync(
    connection_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
) -> dict[str, str]:
    connection = await _connection(request, context.tenant_id, connection_id)
    if connection.status != "ACTIVE":
        raise ConflictError("DRIVE_NOT_ACTIVE", "Resume the Drive connection before syncing")
    checkpoint = await request.state.db.get(DriveCheckpoint, connection.id)
    checkpoint.status = "PENDING"
    checkpoint.next_sync_at = datetime.now(UTC)
    checkpoint.last_error = None
    add_audit_event(
        request.state.db,
        request,
        context,
        action="drive.force_sync",
        resource_type="drive_connection",
        resource_id=connection.id,
    )
    return {"connection_id": connection.id, "status": checkpoint.status}


async def _set_status(connection_id, target, request, context):
    connection = await _connection(request, context.tenant_id, connection_id)
    connection.status = target
    checkpoint = await request.state.db.get(DriveCheckpoint, connection.id)
    checkpoint.status = "PAUSED" if target == "PAUSED" else "PENDING"
    checkpoint.next_sync_at = None if target == "PAUSED" else datetime.now(UTC)
    add_audit_event(
        request.state.db,
        request,
        context,
        action=f"drive.{target.lower()}",
        resource_type="drive_connection",
        resource_id=connection.id,
    )
    return {"connection_id": connection.id, "status": connection.status}


@router.post("/drive/connections/{connection_id}/pause")
async def pause_sync(
    connection_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
) -> dict[str, str]:
    return await _set_status(connection_id, "PAUSED", request, context)


@router.post("/drive/connections/{connection_id}/resume")
async def resume_sync(
    connection_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
) -> dict[str, str]:
    return await _set_status(connection_id, "ACTIVE", request, context)


@router.delete("/drive/connections/{connection_id}", status_code=202)
async def disconnect_drive(
    connection_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
) -> dict[str, str]:
    connection = await _connection(request, context.tenant_id, connection_id)
    connection.status = "DISCONNECTED"
    checkpoint = await request.state.db.get(DriveCheckpoint, connection.id)
    checkpoint.status = "DISCONNECTED"
    checkpoint.next_sync_at = None
    add_audit_event(
        request.state.db,
        request,
        context,
        action="drive.disconnected",
        resource_type="drive_connection",
        resource_id=connection.id,
    )
    return {"connection_id": connection.id, "status": connection.status}


@router.get("/drive/connections/{connection_id}/errors", response_model=list[DriveErrorOut])
async def sync_errors(
    connection_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
    limit: int = Query(50, ge=1, le=200),
) -> list[DriveErrorOut]:
    await _connection(request, context.tenant_id, connection_id)
    rows = await request.state.db.scalars(
        select(DriveChangeEvent)
        .where(
            DriveChangeEvent.connection_id == connection_id,
            DriveChangeEvent.status == "FAILED",
        )
        .order_by(DriveChangeEvent.created_at.desc())
        .limit(limit)
    )
    return [
        DriveErrorOut(
            id=item.id,
            file_id=item.file_id,
            action=item.action,
            error=item.last_error or "Unknown synchronization error",
            created_at=item.created_at,
        )
        for item in rows.all()
    ]


@router.get("/ingestion/queue-health", response_model=QueueHealthOut)
async def queue_health(
    request: Request,
    context: RequestContext = Depends(require_capability("ADMIN")),
) -> QueueHealthOut:
    rows = await request.state.db.execute(
        select(IngestionReceipt.status, func.count(IngestionReceipt.id))
        .where(IngestionReceipt.tenant_id == context.tenant_id)
        .group_by(IngestionReceipt.status)
    )
    dlq_messages = None
    queue = getattr(request.app.state, "event_queue", None)
    if queue is not None:
        dlq_messages = await queue.dlq_message_count()
    return QueueHealthOut(
        enabled=request.app.state.settings.event_ingestion.enabled,
        dlq_messages=dlq_messages,
        alert=bool(dlq_messages and dlq_messages > 0),
        receipt_counts={status: count for status, count in rows.all()},
    )
