# Phase 7 — Authentication, RBAC and Multi-Tenancy

## Cognito JWT validation

FastAPI accepts bearer tokens, reads `kid` without trusting claims, fetches issuer JWKS, caches keys
for the configured TTL, converts the matching RSA JWK, and verifies signature, algorithm, audience,
issuer, expiration, issued-at, subject, and configurable clock skew. Unknown keys, missing claims,
expired tokens, and modified signatures produce structured 403 responses.

Claims resolve the external subject and tenant. PostgreSQL must also contain an active user and
active tenant membership; possession of a valid Cognito token alone is insufficient.

## Roles and capabilities

| Capability | Admin | Editor | Viewer |
|---|---:|---:|---:|
| Query/chat | Yes | Yes | Yes |
| Upload/version/reindex | Yes | Yes | No |
| Delete | Yes | Yes | No |
| Document permissions | Yes | Yes | No |
| User management | Yes | No | No |
| Admin dashboard/audit | Yes | No | No |

Role checks are FastAPI dependencies attached to routes. UI hiding is never treated as security.

## Request context

Every protected request resolves:

- application `user_id`
- Cognito external subject
- `tenant_id`
- membership role
- membership/token groups
- email

Client-provided tenant IDs are not used to scope queries.

## Authorization before retrieval

The ACL resolver selects only active documents in the tenant that are owned by the user or grant
QUERY to the tenant, user, or one of the user's groups. Admins receive active tenant documents.

That exact set is passed into Qdrant as a `tenant_id` AND `document_id MatchAny` filter. An empty
set returns without vector search. SQLite BM25 also adds tenant and document-ID predicates in SQL.
Unauthorized chunks therefore never enter fusion, reranking, prompts, traces, or model context.

## Security tests

Automated tests prove:

- Tenant A's allowed document set excludes Tenant B and ungranted Tenant A documents.
- Viewer cannot delete documents.
- Viewer/editor capability boundaries prevent user management.
- Missing bearer token is rejected.
- Expired RS256 JWT is rejected.
- Modified RS256 JWT is rejected.

Add integration tests against the real Cognito user pool and Qdrant filter telemetry before launch.

## Remaining production controls

- Cognito authorization-code state/nonce and refresh-token rotation.
- Distributed rate limiting and abuse controls.
- Group lifecycle synchronization and membership revocation latency targets.
- Audit export/retention/immutability.
- Permission-change race and cache invalidation testing.
- Penetration tests for object-level authorization and prompt/document injection.

## Exit checklist

See [the Phase 7 exit-criteria runbook](EXIT_CRITERIA_RUNBOOK.md) for the
reproducible Cognito, PostgreSQL, RBAC, and tenant-isolation validation steps.

- [ ] Real JWKS rotation succeeds without restart.
- [ ] Expired, missing, malformed, wrong-audience, wrong-issuer, and modified tokens fail.
- [ ] Admin/editor/viewer matrix is covered at route level.
- [ ] Cross-tenant document, job, chat, audit, and user IDs return no data.
- [ ] Qdrant receives tenant and authorized document filters before search.
- [ ] Unauthorized chunk IDs never appear in answer traces.
