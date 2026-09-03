from __future__ import annotations

from functools import partial

from anyio import to_thread
from fastapi import APIRouter, Depends, Request

from rag_platform.api.acl import authorized_document_ids
from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.api.schemas import SearchRequest

router = APIRouter(prefix="/api/v1/generation", tags=["generation"])


@router.post("/answer")
async def answer(
    body: SearchRequest,
    request: Request,
    context: RequestContext = Depends(require_capability("QUERY")),
) -> dict:
    document_ids = await authorized_document_ids(request.state.db, context)
    service = request.app.state.get_generation(context.tenant_id)
    response = await to_thread.run_sync(
        partial(service.answer, body.query, document_ids=document_ids)
    )
    return response.model_dump()
