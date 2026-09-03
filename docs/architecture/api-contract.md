# API Contract

The developer UI implements two intentionally temporary endpoints:

```text
POST /api/search  {"query": "...", "top_k": 5}
POST /api/ask     {"query": "..."}
```

The future authenticated public API retains these versioned resource boundaries:

```text
/api/v1/auth/*
/api/v1/users/*
/api/v1/tenants/*
/api/v1/documents/*
/api/v1/ingestion/*
/api/v1/chat/*
/api/v1/search/*
/api/v1/admin/*
/api/v1/health/*
```

Phase 5 implements the versioned boundaries as modular FastAPI routers. Kubernetes probes remain
unversioned at `GET /live` and `GET /ready`; liveness is process-only while readiness checks
configured critical dependencies. Interactive OpenAPI is served at `/docs`.

Phase 9–10 add the following Admin-only tenant-scoped operations:

```text
GET    /api/v1/admin/ingestion/queue-health
POST   /api/v1/admin/drive/connections
GET    /api/v1/admin/drive/connections
POST   /api/v1/admin/drive/connections/{id}/force-sync
POST   /api/v1/admin/drive/connections/{id}/pause
POST   /api/v1/admin/drive/connections/{id}/resume
DELETE /api/v1/admin/drive/connections/{id}
GET    /api/v1/admin/drive/connections/{id}/errors
```

## Resource rules

- Version the public API at the path boundary.
- Use tenant scope derived from authenticated claims, never arbitrary client-provided tenant IDs without authorization.
- Use stable document IDs independent of filenames.
- Long-running ingestion operations return job/document identifiers instead of holding HTTP connections open.
- Pagination is required for collection endpoints.
- OpenAPI will be generated from FastAPI in the application phase.
