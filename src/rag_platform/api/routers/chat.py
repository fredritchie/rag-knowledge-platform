from __future__ import annotations

from functools import partial

from anyio import to_thread
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from rag_platform.api.acl import authorized_document_ids
from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.api.errors import NotFoundError
from rag_platform.api.schemas import (
    ChatAnswer,
    ChatMessageCreate,
    ChatMessageOut,
    ChatSessionCreate,
    ChatSessionOut,
)
from rag_platform.application.db.models import AnswerTrace, ChatMessage, ChatSession

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


async def _session(request: Request, context: RequestContext, session_id: str) -> ChatSession:
    value = await request.state.db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.tenant_id == context.tenant_id,
            ChatSession.user_id == context.user_id,
        )
    )
    if value is None:
        raise NotFoundError("Chat session", session_id)
    return value


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    request: Request,
    context: RequestContext = Depends(require_capability("QUERY")),
) -> list[ChatSession]:
    rows = await request.state.db.scalars(
        select(ChatSession)
        .where(
            ChatSession.tenant_id == context.tenant_id,
            ChatSession.user_id == context.user_id,
            ChatSession.archived_at.is_(None),
        )
        .order_by(ChatSession.updated_at.desc())
    )
    return list(rows.all())


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
async def create_session(
    body: ChatSessionCreate,
    request: Request,
    context: RequestContext = Depends(require_capability("QUERY")),
) -> ChatSession:
    value = ChatSession(tenant_id=context.tenant_id, user_id=context.user_id, title=body.title)
    request.state.db.add(value)
    await request.state.db.flush()
    return value


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_messages(
    session_id: str,
    request: Request,
    context: RequestContext = Depends(require_capability("QUERY")),
) -> list[ChatMessage]:
    await _session(request, context, session_id)
    rows = await request.state.db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return list(rows.all())


@router.post("/sessions/{session_id}/messages", response_model=ChatAnswer)
async def create_message(
    session_id: str,
    body: ChatMessageCreate,
    request: Request,
    context: RequestContext = Depends(require_capability("QUERY")),
) -> ChatAnswer:
    await _session(request, context, session_id)
    user_message = ChatMessage(
        tenant_id=context.tenant_id,
        session_id=session_id,
        role="user",
        content=body.content,
    )
    request.state.db.add(user_message)
    await request.state.db.flush()
    document_ids = await authorized_document_ids(request.state.db, context)
    service = request.app.state.get_generation(context.tenant_id)
    answer = await to_thread.run_sync(
        partial(service.answer, body.content, document_ids=document_ids)
    )
    assistant_message = ChatMessage(
        tenant_id=context.tenant_id,
        session_id=session_id,
        role="assistant",
        content=answer.answer,
    )
    request.state.db.add(assistant_message)
    await request.state.db.flush()
    request.state.db.add(
        AnswerTrace(
            tenant_id=context.tenant_id,
            message_id=assistant_message.id,
            prompt_version=answer.prompt_version,
            model_version=answer.model,
            embedding_version=request.app.state.settings.embedding.model_version,
            retrieved_chunk_ids=answer.retrieved_chunk_ids,
            source_metadata=[source.model_dump() for source in answer.sources],
            generation_parameters=answer.generation_parameters,
            retrieval_latency_ms=answer.retrieval_latency_ms,
            generation_latency_ms=answer.generation_latency_ms,
            total_latency_ms=answer.latency_ms,
        )
    )
    return ChatAnswer(
        user_message=ChatMessageOut.model_validate(user_message),
        assistant_message=ChatMessageOut.model_validate(assistant_message),
        answer=answer.model_dump(),
    )
