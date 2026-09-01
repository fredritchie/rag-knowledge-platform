import asyncio

import boto3
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from rag_platform.api.audit import add_audit_event
from rag_platform.api.auth import RequestContext, require_capability
from rag_platform.api.errors import ConflictError, NotFoundError
from rag_platform.api.schemas import MembershipCreate, MembershipOut, UserInvitationCreate, UserOut
from rag_platform.application.db.models import TenantMembership, User

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _pool_id(request: Request) -> str:
    return request.app.state.settings.auth.user_pool_id or request.app.state.settings.auth.issuer.rstrip("/").rsplit("/", 1)[-1]


def _cognito(request: Request):
    return getattr(request.app.state, "cognito_admin", None) or boto3.client(
        "cognito-idp", region_name=request.app.state.settings.storage.region
    )


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


@router.post("/invitations", response_model=UserOut, status_code=201)
async def invite_user(body: UserInvitationCreate, request: Request, context: RequestContext = Depends(require_capability("MANAGE_USERS"))) -> User:
    session = request.state.db
    email = body.email.lower()
    if await session.scalar(select(User).where(User.email == email)):
        raise ConflictError("USER_EXISTS", "A platform user with this email already exists")
    response = await asyncio.to_thread(
        _cognito(request).admin_create_user,
        UserPoolId=_pool_id(request), Username=email,
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": request.app.state.settings.auth.tenant_claim, "Value": context.tenant_id},
        ],
        DesiredDeliveryMediums=["EMAIL"],
    )
    attributes = {item["Name"]: item["Value"] for item in response["User"].get("Attributes", [])}
    subject = attributes.get("sub")
    if not subject:
        raise RuntimeError("Cognito did not return a user subject")
    user = User(external_subject=subject, email=email, display_name=body.display_name, status="ACTIVE")
    session.add(user)
    await session.flush()
    session.add(TenantMembership(tenant_id=context.tenant_id, user_id=user.id, role=body.role, groups=[body.role], active=True))
    add_audit_event(session, request, context, action="user.invited", resource_type="user", resource_id=user.id, details={"email": email, "role": body.role})
    return user


@router.post("/{user_id}/password-reset", status_code=202)
async def send_password_reset(user_id: str, request: Request, context: RequestContext = Depends(require_capability("MANAGE_USERS"))) -> dict[str, str]:
    user = await request.state.db.scalar(select(User).join(TenantMembership, TenantMembership.user_id == User.id).where(User.id == user_id, TenantMembership.tenant_id == context.tenant_id, TenantMembership.active.is_(True)))
    if user is None:
        raise NotFoundError("User", user_id)
    await asyncio.to_thread(_cognito(request).admin_reset_user_password, UserPoolId=_pool_id(request), Username=user.email)
    add_audit_event(request.state.db, request, context, action="user.password_reset_sent", resource_type="user", resource_id=user.id)
    return {"user_id": user.id, "status": "RESET_EMAIL_SENT"}
