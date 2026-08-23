from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from rag_platform.api.auth import RequestContext, request_context
from rag_platform.api.errors import NotFoundError
from rag_platform.api.schemas import TenantOut
from rag_platform.application.db.models import Tenant

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


@router.get("/current", response_model=TenantOut)
async def current_tenant(
    request: Request, context: RequestContext = Depends(request_context)
) -> Tenant:
    tenant = await request.state.db.scalar(select(Tenant).where(Tenant.id == context.tenant_id))
    if tenant is None:
        raise NotFoundError("Tenant", context.tenant_id)
    return tenant
