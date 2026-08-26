# Phase 5 — PostgreSQL Persistence Foundation

## Objective

Introduce the PostgreSQL application schema, async SQLAlchemy session management, and repeatable
Alembic migrations. Phase 5 establishes persistence boundaries for later API and worker phases; it
does not yet ship those process entry points.

## Implemented runtime boundary

```text
Alembic migration command
        │
        ▼
PostgreSQL application schema
        ▲
        │
SQLAlchemy models and async session factory
```

The Phase 1 SQLite catalog remains the local PDF-processing catalog. PostgreSQL becomes the
application system of record for identity, permissions, logical documents and versions, jobs,
conversations, sync state, audits, and model/prompt/embedding lineage.

API and worker implementations arrive on later branches:

| Runtime | First implemented phase |
|---|---|
| FastAPI application | Phase 8 |
| Ingestion worker | Phase 8 |
| S3 event worker | Phase 9 |
| Source synchronization worker | Phase 10 |

Phase 5 must not advertise or invoke these commands before their importable modules exist.

## PostgreSQL schema

The SQLAlchemy models define:

- `tenants`, `users`, `tenant_memberships`
- `documents`, `document_versions`, `document_permissions`, `document_sources`
- `ingestion_jobs`, `ingestion_events`, `ingestion_receipts`
- `chat_sessions`, `chat_messages`, `answer_traces`
- `drive_connections`, `drive_sync_state`, `drive_checkpoints`, `drive_change_events`
- `audit_events`
- `model_versions`, `prompt_versions`, `embedding_versions`

IDs are opaque prefixed UUID4 strings. JSON columns retain groups, provider metadata, traces, and
version parameters. Composite uniqueness constraints protect tenant checksum identity, document
version numbers, memberships, permissions, event receipts, and version registries.

Every explicitly named PostgreSQL relation-like object must have a unique name. This includes
tables, indexes, primary keys, and unique constraints. Two ingestion receipt constraints begin
with `provider`, so they use explicit names rather than the default first-column naming rule.

## Configuration

The database settings live in `config/rag.yaml`:

```yaml
database:
  url: postgresql+asyncpg://rag:rag@localhost:5432/rag_platform
  echo: false
  pool_size: 10
  max_overflow: 20
  pool_timeout_seconds: 30
```

Every value supports a `RAG__DATABASE__FIELD` environment override. For example:

```bash
export RAG__DATABASE__URL=postgresql+asyncpg://rag:rag@localhost:5432/rag_platform
```

## Migrations

Start PostgreSQL and apply the committed migration chain:

```bash
make services-up
make migrate
alembic current
```

The Phase 5 head is `20260823_0001`.

Generate a new revision only after intentionally changing the SQLAlchemy schema:

```bash
alembic revision --autogenerate -m "add <specific schema change>"
```

Always inspect the generated file before applying it. Do not run the placeholder command merely to
verify Phase 5: Alembic creates a new revision even when autogenerate finds no operations.

Apply an intentionally reviewed revision with:

```bash
alembic upgrade head
```

Application startup must not create or mutate the production schema. Alembic owns schema changes.

## Run

The complete Phase 5 runtime procedure is:

```bash
make services-up
make migrate
alembic heads
alembic current
docker compose ps
```

`alembic heads` and `alembic current` must both report `20260823_0001`. Compose must report healthy
or running PostgreSQL, Qdrant, and Ollama containers.

Confirm the database revision directly when needed:

```bash
docker compose exec postgres \
  psql -U rag -d rag_platform \
  -c "SELECT version_num FROM alembic_version;"
```

Do not run `rag-api`, `rag-ingestion-worker`, `rag-s3-event-worker`, or `rag-sync-worker` on this
branch. Their packages are not part of Phase 5.

## Verification

The Phase 5 regression test verifies that PostgreSQL relation-like names generated from the
metadata are unique. This prevents two unique constraints from producing the same backing-index
name during `CREATE TABLE`.

Production acceptance still requires applying the committed migration against real PostgreSQL:

```bash
pytest tests/test_phase5_schema.py
make migrate
```

## Exit checklist

- [ ] `docker compose config --services` lists PostgreSQL, Qdrant, and Ollama.
- [ ] PostgreSQL reports that it is accepting connections.
- [ ] Metadata contains no duplicate relation-like names.
- [ ] The committed migration applies successfully to PostgreSQL.
- [ ] `alembic heads` reports only `20260823_0001`.
- [ ] `alembic current` reports `20260823_0001 (head)`.
- [ ] The `alembic_version` table contains `20260823_0001`.
- [ ] No untracked placeholder migrations remain under `migrations/versions/`.
- [ ] The async database engine and session factory dispose connections cleanly.
