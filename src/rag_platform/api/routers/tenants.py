from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from rag_platform.api.auth import RequestContext, request_context
from rag_platform.api.errors import ConflictError, ForbiddenError, NotFoundError
from rag_platform.api.schemas import TenantCreate, TenantOut
from rag_platform.application.db.models import Tenant, TenantMembership

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    request: Request, context: RequestContext = Depends(request_context)
) -> list[Tenant]:
    result = await request.state.db.scalars(
        select(Tenant)
        .join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
        .where(TenantMembership.user_id == context.user_id, TenantMembership.active.is_(True))
        .order_by(Tenant.name)
    )
    return list(result.all())


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantCreate, request: Request, context: RequestContext = Depends(request_context)
) -> Tenant:
    if context.role != "ADMIN":
        raise ForbiddenError()
    session = request.state.db
    if await session.scalar(select(Tenant.id).where(Tenant.slug == body.slug)):
        raise ConflictError("TENANT_SLUG_EXISTS", "A tenant with this slug already exists")
    tenant = Tenant(name=body.name, slug=body.slug, status="ACTIVE", settings={})
    session.add(tenant)
    await session.flush()
    session.add(TenantMembership(tenant_id=tenant.id, user_id=context.user_id, role="ADMIN", groups=["ADMIN"], active=True))
    await session.flush()
    return tenant


@router.get("/current", response_model=TenantOut)
async def current_tenant(
    request: Request, context: RequestContext = Depends(request_context)
) -> Tenant:
    tenant = await request.state.db.scalar(select(Tenant).where(Tenant.id == context.tenant_id))
    if tenant is None:
        raise NotFoundError("Tenant", context.tenant_id)
    return tenant
