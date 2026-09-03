# Phase 8 — Document Lifecycle and Manual Upload

> Phase 9 deployments set `event_ingestion.enabled=true`. In that mode, upload completion leaves
> the job in `WAITING_EVENT`; the canonical S3 EventBridge/SQS message, not the browser callback,
> authorizes processing. See the Phase 9 operating guide for the durable path.

## Canonical storage flow

```text
Browser hashes PDF
  → FastAPI validates tenant, role, checksum and metadata
  → PostgreSQL creates logical document/version/job
  → FastAPI returns encrypted S3 presigned POST
  → Browser uploads directly to S3
  → Browser acknowledges completion
  → job becomes QUEUED
  → ingestion worker claims and processes version
```

S3 is canonical for application uploads. Local Phase 1 copies remain development artifacts.

## Identity and duplicate handling

Logical documents have stable IDs independent of names. Versions contain checksum, S3 key, source
version, size, processing versions, counts, status, and activation times. Exact SHA-256 duplicates
are rejected per tenant before presigning. Filename is normalized to its basename before creating
the key.

The S3 key is tenant/document/version scoped. Presigned POST expiration, endpoint, region, bucket,
AES256/KMS encryption, and optional KMS key are configurable.

## Safe updates

Uploading with `document_id` creates the next version but does not change `current_version_id`.
The worker processor must parse, chunk, embed, index, and validate the replacement first. Only a
successful result atomically:

1. Marks the new version ACTIVE.
2. Records parser/chunker/embedding versions and counts.
3. Points the logical document at the new version.
4. Marks the old version INACTIVE.

Failure marks only the replacement failed when an older active version exists. The working version
continues serving queries. Vector cleanup for the old inactive version belongs after successful
activation in the concrete processor adapter, never before.

## Job and event visibility

Jobs store type, status, stage, progress, attempts, worker, error, and timing. Events provide an
append-only stage history consumed by document detail and ingestion status screens. Upload
authorization creates WAITING_UPLOAD; acknowledgement queues it.

## Deletion and reindex

Delete and reindex are asynchronous jobs. Delete first marks the document DELETING; the concrete
processor must remove vectors and canonical objects according to retention policy before marking
DELETED. Reindex targets the current version without replacing document identity.

## Important adapter boundary

This repository implements orchestration, persistence, safe switching, and tested processor
protocols. The command-line worker intentionally ships with an unconfigured processor that fails
visibly. A deployment must inject its concrete S3 download, Phase 1 parser/chunker, embedding,
Qdrant upsert/validation, old-vector cleanup, and S3 deletion adapter. This prevents a scaffold from
claiming a document is active without actually processing it.

## Exit checklist

- [ ] Presigned upload requires editor/admin and tenant membership.
- [ ] S3 policy includes expected key, content type, expiration, and encryption.
- [ ] Completion is accepted only for the document's tenant/version.
- [ ] Duplicate checksum returns the existing document/version IDs.
- [ ] Failed replacement leaves the old version active and searchable.
- [ ] Successful replacement activates new vectors before deactivating/cleaning old vectors.
- [ ] Job stages and errors are visible in API/UI.
- [ ] Delete/reindex are asynchronous and audited.
- [ ] Concrete production processor and deletion adapters pass end-to-end tests.
