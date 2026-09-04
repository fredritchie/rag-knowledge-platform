from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.api.errors import ForbiddenError
from rag_platform.application.db.models import TenantMembership, User
from rag_platform.config import AuthSettings
from rag_platform.observability import observe_stage, set_tenant_id

bearer = HTTPBearer(auto_error=False)


class TokenClaims(BaseModel):
    subject: str
    tenant_id: str
    email: str | None = None
    roles: list[str]
    groups: list[str]
    raw: dict[str, Any]


class RequestContext(BaseModel):
    user_id: str
    external_subject: str
    tenant_id: str
    email: str | None
    role: str
    groups: list[str]


@dataclass(slots=True)
class _JWKSCache:
    expires_at: float = 0
    keys: dict[str, Any] | None = None


class CognitoJWTVerifier:
    def __init__(self, config: AuthSettings, client: httpx.AsyncClient | None = None):
        self.config = config
        self.client = client
        self.cache = _JWKSCache()

    @property
    def jwks_url(self) -> str:
        return self.config.jwks_url or f"{self.config.issuer.rstrip('/')}/.well-known/jwks.json"

    async def _keys(self) -> dict[str, Any]:
        if self.cache.keys is not None and self.cache.expires_at > time.monotonic():
            return self.cache.keys
        if self.client is not None:
            response = await self.client.get(self.jwks_url)
            response.raise_for_status()
            body = response.json()
        else:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                body = response.json()
        keys = {key["kid"]: key for key in body.get("keys", [])}
        self.cache = _JWKSCache(
            expires_at=time.monotonic() + self.config.jwks_cache_seconds, keys=keys
        )
        return keys

    async def verify(self, token: str) -> TokenClaims:
        with observe_stage("auth.validate"):
            try:
                _require_canonical_jwt(token)
                header = jwt.get_unverified_header(token)
                key_data = (await self._keys()).get(header.get("kid"))
                if not key_data:
                    raise jwt.InvalidTokenError("Unknown signing key")
                key = RSAAlgorithm.from_jwk(json.dumps(key_data))
                payload = jwt.decode(
                    token,
                    key=key,
                    algorithms=self.config.algorithms,
                    audience=self.config.audience,
                    issuer=self.config.issuer,
                    leeway=self.config.clock_skew_seconds,
                    options={"require": ["exp", "iat", "sub"]},
                )
                tenant_id = str(payload[self.config.tenant_claim])
            except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
                raise ForbiddenError("Invalid or expired bearer token") from exc
        roles = _claim_list(payload.get(self.config.role_claim))
        groups = _claim_list(payload.get(self.config.group_claim))
        return TokenClaims(
            subject=str(payload["sub"]),
            tenant_id=tenant_id,
            email=payload.get("email"),
            roles=[value.upper() for value in roles],
            groups=groups,
            raw=payload,
        )


def _require_canonical_jwt(token: str) -> None:
    """Reject alternate base64url encodings that decode to the same signed bytes."""
    parts = token.split(".")
    if len(parts) != 3:
        raise jwt.InvalidTokenError("JWT must have three segments")
    for part in parts:
        padding = "=" * (-len(part) % 4)
        decoded = base64.urlsafe_b64decode(part + padding)
        canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode()
        if canonical != part:
            raise jwt.InvalidTokenError("JWT uses non-canonical base64url encoding")


def _claim_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


async def token_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> TokenClaims:
    if credentials is None:
        raise ForbiddenError("Missing bearer token")
    return await request.app.state.jwt_verifier.verify(credentials.credentials)


async def request_context(
    request: Request,
    claims: TokenClaims = Depends(token_claims),
) -> RequestContext:
    session: AsyncSession = request.state.db
    # The signed Cognito claim supplies a safe default tenant. A request can
    # select another tenant only when this user has an active membership there.
    requested_tenant_id = request.headers.get("X-Tenant-ID")
    effective_tenant_id = requested_tenant_id or claims.tenant_id
    with observe_stage("authorization.resolve"):
        result = await session.execute(
            select(User, TenantMembership)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                User.external_subject == claims.subject,
                User.status == "ACTIVE",
                TenantMembership.tenant_id == effective_tenant_id,
                TenantMembership.active.is_(True),
            )
        )
        row = result.first()
    if row is None:
        raise ForbiddenError("User is not an active member of this tenant")
    user, membership = row
    request.state.tenant_id = membership.tenant_id
    set_tenant_id(membership.tenant_id)
    return RequestContext(
        user_id=user.id,
        external_subject=user.external_subject,
        tenant_id=membership.tenant_id,
        email=user.email,
        role=membership.role.upper(),
        groups=sorted(set(membership.groups) | set(claims.groups)),
    )


CAPABILITIES = {
    "QUERY": {"ADMIN", "EDITOR", "VIEWER"},
    "UPLOAD": {"ADMIN", "EDITOR"},
    "DELETE": {"ADMIN", "EDITOR"},
    "MANAGE_PERMISSIONS": {"ADMIN", "EDITOR"},
    "MANAGE_USERS": {"ADMIN"},
    "ADMIN": {"ADMIN"},
}


def require_capability(capability: str):
    async def dependency(context: RequestContext = Depends(request_context)) -> RequestContext:
        if context.role not in CAPABILITIES[capability]:
            raise ForbiddenError()
        return context

    return dependency
