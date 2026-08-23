from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import asc, desc, func, select

from rag_platform.api.audit import add_audit_event
from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.api.errors import ConflictError, ForbiddenError, NotFoundError
from rag_platform.api.schemas import (
    DocumentDetail,
    DocumentList,
    DocumentOut,
    DocumentVersionOut,
    PageMeta,
    PermissionCreate,
    UploadAuthorizationRequest,
    UploadAuthorizationResponse,
    UploadCompleteRequest,
)
from rag_platform.application.db.models import (
    Document,
    DocumentPermission,
    DocumentSource,
    DocumentVersion,
    IngestionEvent,
    IngestionJob,
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


async def _tenant_document(session, tenant_id: str, document_id: str) -> Document:
    document = await session.scalar(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    if document is None:
        raise NotFoundError("Document", document_id)
    return document


@router.get("", response_model=DocumentList)
async def list_documents(
    request: Request,
    context: RequestContext = Depends(require_capability("QUERY")),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    source: str | None = None,
    sort: str = Query("updated_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> DocumentList:
    allowed_sort = {
        "updated_at": Document.updated_at,
        "created_at": Document.created_at,
        "filename": Document.filename,
        "status": Document.status,
    }
    if sort not in allowed_sort:
        raise ConflictError("INVALID_SORT", "Unsupported sort field", sort=sort)
    filters = [Document.tenant_id == context.tenant_id, Document.deleted_at.is_(None)]
    if status:
        filters.append(Document.status == status)
    if source:
        filters.append(Document.source == source)
    total = await request.state.db.scalar(select(func.count(Document.id)).where(*filters))
    direction = desc if order == "desc" else asc
    rows = await request.state.db.scalars(
        select(Document)
        .where(*filters)
        .order_by(direction(allowed_sort[sort]), Document.id)
        .limit(limit)
        .offset(offset)
    )
    return DocumentList(
        items=[DocumentOut.model_validate(item) for item in rows.all()],
        page=PageMeta(limit=limit, offset=offset, total=total or 0),
    )


@router.post("/uploads", response_model=UploadAuthorizationResponse, status_code=201)
async def authorize_upload(
    body: UploadAuthorizationRequest,
    request: Request,
    context: RequestContext = Depends(require_capability("UPLOAD")),
) -> UploadAuthorizationResponse:
    session = request.state.db
    checksum = body.checksum_sha256.lower()
    duplicate = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.tenant_id == context.tenant_id,
            DocumentVersion.checksum_sha256 == checksum,
        )
    )
    if duplicate:
        raise ConflictError(
            "DUPLICATE_DOCUMENT",
            "This exact document content already exists in the tenant",
            document_id=duplicate.document_id,
            document_version_id=duplicate.id,
        )

    if body.document_id:
        document = await _tenant_document(session, context.tenant_id, body.document_id)
        maximum = await session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document.id
            )
        )
        version_number = (maximum or 0) + 1
    else:
        document = Document(
            tenant_id=context.tenant_id,
            owner_id=context.user_id,
            filename=Path(body.filename).name,
            source=body.source,
            content_type=body.content_type,
            status="PENDING_UPLOAD",
        )
        session.add(document)
        await session.flush()
        version_number = 1
        session.add(
            DocumentPermission(
                tenant_id=context.tenant_id,
                document_id=document.id,
                principal_type="TENANT",
                principal_id=context.tenant_id,
                capability="QUERY",
            )
        )

    version = DocumentVersion(
        tenant_id=context.tenant_id,
        document_id=document.id,
        version_number=version_number,
        source_version=body.source_version,
        checksum_sha256=checksum,
        storage_key="pending",
        file_size_bytes=body.file_size_bytes,
        status="PENDING_UPLOAD",
    )
    session.add(version)
    await session.flush()
    safe_name = Path(body.filename).name.replace("/", "_")
    version.storage_key = (
        f"tenants/{context.tenant_id}/documents/{document.id}/versions/{version.id}/{safe_name}"
    )
    job = IngestionJob(
        tenant_id=context.tenant_id,
        document_id=document.id,
        document_version_id=version.id,
        status="WAITING_UPLOAD",
        stage="RECEIVED",
    )
    session.add(job)
    if body.source_file_id:
        session.add(
            DocumentSource(
                tenant_id=context.tenant_id,
                document_id=document.id,
                source_type=body.source,
                source_file_id=body.source_file_id,
                source_version=body.source_version,
            )
        )
    await session.flush()
    upload = request.app.state.storage.create_upload(version.storage_key, body.content_type)
    add_audit_event(
        session,
        request,
        context,
        action="document.upload_authorized",
        resource_type="document",
        resource_id=document.id,
        details={"version": version_number, "job_id": job.id},
    )
    return UploadAuthorizationResponse(
        document_id=document.id,
        document_version_id=version.id,
        version_number=version_number,
        ingestion_job_id=job.id,
        storage_key=version.storage_key,
        upload_url=upload["url"],
        upload_fields=upload["fields"],
        expires_in_seconds=request.app.state.settings.storage.upload_expiry_seconds,
    )


@router.post("/{document_id}/upload-complete", status_code=202)
async def upload_complete(
    document_id: str,
    body: UploadCompleteRequest,
    request: Request,
    context: RequestContext = Depends(require_capability("UPLOAD")),
) -> dict[str, str]:
    session = request.state.db
    document = await _tenant_document(session, context.tenant_id, document_id)
    version = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.id == body.document_version_id,
            DocumentVersion.document_id == document.id,
            DocumentVersion.tenant_id == context.tenant_id,
        )
    )
    if version is None:
        raise NotFoundError("Document version", body.document_version_id)
    job = await session.scalar(
        select(IngestionJob).where(IngestionJob.document_version_id == version.id)
    )
    if job is None:
        raise NotFoundError("Ingestion job", version.id)
    if version.status == "PENDING_UPLOAD":
        event_driven = request.app.state.settings.event_ingestion.enabled
        version.status = "WAITING_EVENT" if event_driven else "RECEIVED"
        if document.current_version_id is None:
            document.status = "WAITING_EVENT" if event_driven else "RECEIVED"
        job.status = "WAITING_EVENT" if event_driven else "QUEUED"
        session.add(
            IngestionEvent(
                tenant_id=context.tenant_id,
                job_id=job.id,
                stage="RECEIVED",
                status=job.status,
                message=(
                    "Upload completion acknowledged; waiting for the canonical S3 event."
                    if event_driven
                    else "Upload completion acknowledged; ingestion queued."
                ),
            )
        )
    add_audit_event(
        session,
        request,
        context,
        action="document.upload_completed",
        resource_type="document_version",
        resource_id=version.id,
    )
    return {"document_id": document.id, "job_id": job.id, "status": job.status}


@router.get("/{document_id}", response_model=DocumentDetail)
async def document_detail(
    document_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("QUERY")),
) -> DocumentDetail:
    session = request.state.db
    document = await _tenant_document(session, context.tenant_id, document_id)
    versions = list(
        (
            await session.scalars(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document.id)
                .order_by(DocumentVersion.version_number.desc())
            )
        ).all()
    )
    permissions = list(
        (
            await session.scalars(
                select(DocumentPermission).where(DocumentPermission.document_id == document.id)
            )
        ).all()
    )
    jobs = list(
        (
            await session.scalars(
                select(IngestionJob)
                .where(IngestionJob.document_id == document.id)
                .order_by(IngestionJob.created_at.desc())
            )
        ).all()
    )
    return DocumentDetail(
        document=DocumentOut.model_validate(document),
        versions=[DocumentVersionOut.model_validate(item) for item in versions],
        permissions=[
            {
                "id": item.id,
                "principal_type": item.principal_type,
                "principal_id": item.principal_id,
                "capability": item.capability,
            }
            for item in permissions
        ],
        ingestion_jobs=[
            {
                "id": item.id,
                "status": item.status,
                "stage": item.stage,
                "progress_percent": item.progress_percent,
                "error_code": item.error_code,
                "error_message": item.error_message,
            }
            for item in jobs
        ],
    )


@router.post("/{document_id}/permissions", status_code=201)
async def grant_permission(
    document_id: str,
    body: PermissionCreate,
    request: Request,
    context: RequestContext = Depends(require_capability("MANAGE_PERMISSIONS")),
) -> dict[str, str]:
    document = await _tenant_document(request.state.db, context.tenant_id, document_id)
    if context.role == "EDITOR" and body.capability != "QUERY":
        raise ForbiddenError("Editors may grant query access only")
    permission = DocumentPermission(
        tenant_id=context.tenant_id,
        document_id=document.id,
        principal_type=body.principal_type,
        principal_id=body.principal_id,
        capability=body.capability,
    )
    request.state.db.add(permission)
    await request.state.db.flush()
    add_audit_event(
        request.state.db,
        request,
        context,
        action="document.permission_granted",
        resource_type="document",
        resource_id=document.id,
        details=body.model_dump(),
    )
    return {"permission_id": permission.id}


@router.post("/{document_id}/reindex", status_code=202)
async def reindex_document(
    document_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("UPLOAD")),
) -> dict[str, str]:
    document = await _tenant_document(request.state.db, context.tenant_id, document_id)
    if not document.current_version_id:
        raise ConflictError("NO_ACTIVE_VERSION", "Document has no active version")
    job = IngestionJob(
        tenant_id=context.tenant_id,
        document_id=document.id,
        document_version_id=document.current_version_id,
        job_type="REINDEX",
        status="QUEUED",
        stage="EMBEDDING",
    )
    request.state.db.add(job)
    await request.state.db.flush()
    return {"job_id": job.id, "status": job.status}


@router.delete("/{document_id}", status_code=202)
async def delete_document(
    document_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("DELETE")),
) -> dict[str, str]:
    document = await _tenant_document(request.state.db, context.tenant_id, document_id)
    document.status = "DELETING"
    document.deleted_at = datetime.now(UTC)
    target_version_id = document.current_version_id
    if target_version_id is None:
        target_version_id = await request.state.db.scalar(
            select(DocumentVersion.id)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
    if target_version_id is None:
        raise ConflictError("NO_DOCUMENT_VERSION", "Document has no version to delete")
    job = IngestionJob(
        tenant_id=context.tenant_id,
        document_id=document.id,
        document_version_id=target_version_id,
        job_type="DELETE",
        status="QUEUED",
        stage="DELETING",
    )
    request.state.db.add(job)
    await request.state.db.flush()
    add_audit_event(
        request.state.db,
        request,
        context,
        action="document.delete_requested",
        resource_type="document",
        resource_id=document.id,
    )
    return {"document_id": document.id, "job_id": job.id, "status": "DELETING"}
