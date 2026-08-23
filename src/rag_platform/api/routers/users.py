from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from rag_platform.api.audit import add_audit_event
from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.api.schemas import MembershipCreate, MembershipOut, UserOut
from rag_platform.application.db.models import TenantMembership, User

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(
    request: Request,
    context: RequestContext = Depends(require_capability("MANAGE_USERS")),
) -> list[User]:
    result = await request.state.db.scalars(
        select(User)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(TenantMembership.tenant_id == context.tenant_id)
        .order_by(User.email)
    )
    return list(result.all())


@router.post("/memberships", response_model=MembershipOut, status_code=201)
async def create_membership(
    body: MembershipCreate,
    request: Request,
    context: RequestContext = Depends(require_capability("MANAGE_USERS")),
) -> TenantMembership:
    session = request.state.db
    user = await session.scalar(select(User).where(User.external_subject == body.external_subject))
    if user is None:
        user = User(
            external_subject=body.external_subject,
            email=body.email,
            display_name=body.display_name,
        )
        session.add(user)
        await session.flush()
    membership = await session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == context.tenant_id,
            TenantMembership.user_id == user.id,
        )
    )
    if membership is None:
        membership = TenantMembership(
            tenant_id=context.tenant_id,
            user_id=user.id,
            role=body.role,
            groups=body.groups,
        )
        session.add(membership)
    else:
        membership.role = body.role
        membership.groups = body.groups
        membership.active = True
    await session.flush()
    add_audit_event(
        session,
        request,
        context,
        action="membership.upsert",
        resource_type="tenant_membership",
        resource_id=membership.id,
        details={"role": body.role},
    )
    return membership
