# Services

The deployable services are implemented in the main Python package and the
`apps/web` frontend:

- `rag-api` starts the FastAPI application.
- `rag-ingestion-worker` processes queued document versions.
- `rag-s3-event-worker` consumes durable EventBridge/SQS events and runs the concrete S3 pipeline.
- `rag-sync-worker` processes external-source synchronization work.
- `apps/web` contains the Next.js application.

PostgreSQL, Qdrant, and Ollama development dependencies are declared in the
root `compose.yaml`. Keeping the service entry points in the package avoids
duplicating application code in thin service-specific directories.
