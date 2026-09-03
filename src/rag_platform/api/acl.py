from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.api.auth import RequestContext
from rag_platform.application.db.models import Document, DocumentPermission


async def authorized_document_ids(session: AsyncSession, context: RequestContext) -> set[str]:
    base = [Document.tenant_id == context.tenant_id, Document.status == "ACTIVE"]
    if context.role == "ADMIN":
        result = await session.scalars(select(Document.id).where(*base))
        return set(result.all())

    principals = [
        and_(
            DocumentPermission.principal_type == "TENANT",
            DocumentPermission.principal_id == context.tenant_id,
        ),
        and_(
            DocumentPermission.principal_type == "USER",
            DocumentPermission.principal_id == context.user_id,
        ),
    ]
    if context.groups:
        principals.append(
            and_(
                DocumentPermission.principal_type == "GROUP",
                DocumentPermission.principal_id.in_(context.groups),
            )
        )
    statement = (
        select(Document.id)
        .outerjoin(
            DocumentPermission,
            and_(
                DocumentPermission.document_id == Document.id,
                DocumentPermission.tenant_id == context.tenant_id,
                DocumentPermission.capability == "QUERY",
            ),
        )
        .where(*base, or_(Document.owner_id == context.user_id, *principals))
        .distinct()
    )
    return set((await session.scalars(statement)).all())
