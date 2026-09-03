# Phase 5 — Backend Application and PostgreSQL

## Objective

Turn the local prototype into one modular FastAPI application backed by PostgreSQL, while keeping
ingestion and source synchronization as separately scalable worker processes. This phase does not
split the application into premature network services.

## Runtime architecture

```text
FastAPI application
├── auth and request context
├── tenant and user membership
├── documents, versions, ACLs and S3 upload authorization
├── ingestion jobs and events
├── ACL-scoped retrieval and generation
├── persistent chat and answer traces
├── admin dashboard
└── audit events

Separate processes
├── rag-ingestion-worker
└── rag-sync-worker
```

The Phase 1 SQLite catalog remains the local PDF-processing catalog. PostgreSQL is the application
system of record for identity, permissions, logical documents and versions, jobs, conversations,
sync state, audits, and model/prompt/embedding lineage.

## PostgreSQL schema

The SQLAlchemy models define:

- `tenants`, `users`, `tenant_memberships`
- `documents`, `document_versions`, `document_permissions`, `document_sources`
- `ingestion_jobs`, `ingestion_events`
- `chat_sessions`, `chat_messages`, `answer_traces`
- `drive_connections`, `drive_sync_state`
- `audit_events`
- `model_versions`, `prompt_versions`, `embedding_versions`

All tenant-owned query paths include tenant predicates. IDs are opaque prefixed UUID4 strings.
JSON columns retain groups, provider metadata, traces, and version parameters. Composite uniqueness
constraints protect tenant checksum identity, document version numbers, memberships, permissions,
and version registries.

## Configuration

Application settings live beside existing RAG settings in `config/rag.yaml`:

- `database`: async SQLAlchemy URL and pool behavior.
- `api`: bind address, CORS, paging, request ID and rate-limit hook.
- `auth`: Cognito issuer/audience/JWKS and claim mapping.
- `storage`: S3 bucket, region, endpoint, expiry, and encryption.
- `health`: critical readiness checks and timeouts.
- `worker`: polling, claim batch, attempts, and heartbeat policy.

Every value supports `RAG__SECTION__FIELD` environment overrides.

## Migrations

Alembic owns the application schema:

```bash
make services-up
make migrate
```

The async migration environment reads the effective centralized database URL. The initial revision
is `20260823_0001`. Generate future revisions with:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Never replace a production schema by calling `create_all`; application startup deliberately does
not mutate schema.

## FastAPI features

- Modular routers under `src/rag_platform/api/routers`.
- Pydantic request/response schemas and generated OpenAPI at `/docs` and `/openapi.json`.
- Dependency injection for identity and capability enforcement.
- Structured errors containing code, message, request ID, and details.
- Caller-supplied or generated `X-Request-ID` propagated in responses and audit events.
- Limit/offset pagination, filtering, allow-listed sorting, and deterministic tie-breaking.
- In-memory fixed-window rate-limit hook with response headers. Replace with a distributed adapter
  before horizontal scaling.
- CORS allow-list configuration.
- Async session per request/task; sessions are never shared across concurrent tasks.

## API modules

| Module | Prefix |
|---|---|
| Auth | `/api/v1/auth` |
| Tenant | `/api/v1/tenants` |
| Users | `/api/v1/users` |
| Documents | `/api/v1/documents` |
| Ingestion | `/api/v1/ingestion` |
| Retrieval | `/api/v1/search` |
| Generation | `/api/v1/generation` |
| Chat | `/api/v1/chat` |
| Admin | `/api/v1/admin` |
| Audit | `/api/v1/audit` |

## Health semantics

`GET /live` checks only that the process can answer. It does not call PostgreSQL, Qdrant, Ollama,
S3, or Cognito. Dependency outages therefore do not cause Kubernetes to restart a healthy process.

`GET /ready` checks only dependencies enabled under `health`. It returns 503 and per-dependency
status when a critical dependency is unavailable. Ollama is disabled from readiness by default
because deployments may choose degradation rather than removing all API capacity.

## Workers

Workers claim rows with `FOR UPDATE SKIP LOCKED`, bounded batches, attempt counters, worker IDs,
and persisted events. Processor and Drive adapters are protocols. The default command uses an
explicit unconfigured adapter and fails jobs visibly; deployments must inject the concrete
S3/parser/index or Drive connector implementation rather than silently reporting success.

## Run

```bash
make services-up
make migrate
rag-api
rag-ingestion-worker
rag-sync-worker
```

API bind defaults to `127.0.0.1:8080`. Configure a production reverse proxy/TLS boundary.

## Verification

Tests use async SQLite only as a disposable PostgreSQL-compatible test adapter. They validate
schema creation, health semantics, OpenAPI, request IDs, structured auth rejection, ACL filtering,
upload/version behavior, and worker activation. The Alembic head is also executable against the
test adapter. Production acceptance still requires a real PostgreSQL migration and concurrency run.

## Exit checklist

- [ ] PostgreSQL starts and Alembic reaches head.
- [ ] OpenAPI contains every modular resource boundary.
- [ ] Request IDs appear in successful and error responses.
- [ ] `/live` remains healthy during dependency outages.
- [ ] `/ready` fails when configured critical dependencies fail.
- [ ] Pagination, filtering, and sorting are bounded.
- [ ] Worker claims cannot be processed twice concurrently.
- [ ] Application and worker processes shut down/dispose pools cleanly.
