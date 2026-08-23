from __future__ import annotations

from functools import partial

from anyio import to_thread
from fastapi import APIRouter, Depends, Request

from rag_platform.api.acl import authorized_document_ids
from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.api.schemas import SearchRequest, SearchResponse

router = APIRouter(prefix="/api/v1/search", tags=["retrieval"])


@router.post("", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    request: Request,
    context: RequestContext = Depends(require_capability("QUERY")),
) -> SearchResponse:
    document_ids = await authorized_document_ids(request.state.db, context)
    retrieval = request.app.state.get_retrieval(context.tenant_id)
    results, latency = await to_thread.run_sync(
        partial(
            retrieval.search,
            body.query,
            top_k=body.top_k,
            mode=body.mode,
            document_ids=document_ids,
        )
    )
    return SearchResponse(
        query=body.query,
        latency_ms=latency,
        authorized_document_count=len(document_ids),
        results=[result.model_dump() for result in results],
    )
