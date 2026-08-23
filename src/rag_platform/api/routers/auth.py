from fastapi import APIRouter, Depends

from rag_platform.api.auth import RequestContext, request_context
from rag_platform.api.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUser)
async def me(context: RequestContext = Depends(request_context)) -> CurrentUser:
    return CurrentUser(**context.model_dump())
