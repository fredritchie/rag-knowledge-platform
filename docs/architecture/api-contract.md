# Initial API Contract

The HTTP API is not implemented in Phase 0/1; this file fixes the first public resource boundaries so later FastAPI work does not invent endpoints ad hoc.

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

## Resource rules

- Version the public API at the path boundary.
- Use tenant scope derived from authenticated claims, never arbitrary client-provided tenant IDs without authorization.
- Use stable document IDs independent of filenames.
- Long-running ingestion operations return job/document identifiers instead of holding HTTP connections open.
- Pagination is required for collection endpoints.
- OpenAPI will be generated from FastAPI in the application phase.
