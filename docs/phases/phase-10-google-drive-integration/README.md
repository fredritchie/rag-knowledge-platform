# Phase 10 — Google Drive Integration

## Outcome

Google Drive is implemented as a source adapter, not as another RAG pipeline:

```text
Google Drive Changes API
  -> rag-sync-worker
  -> canonical versioned S3 object or SQS delete event
  -> EventBridge
  -> Phase 9 SQS worker
  -> existing parse/chunk/embed/index/delete lifecycle
```

Drive synchronization polls every five minutes by default. The interval, page size, endpoints,
shared-drive support, canonical key layout, secret region, and Google Workspace export MIME types
are configuration fields.

## Source map

| Concern | Implementation |
|---|---|
| Google OAuth secret resolution | `SecretsManagerCredentialsResolver` |
| Changes API/start token/pagination | `GoogleDriveClient` |
| Durable sync and change handling | `DriveSyncService` |
| Due-connection scheduler | `SyncWorker` |
| State and per-change errors | `DriveCheckpoint`, `DriveChangeEvent` |
| Canonical object/document mapping | `DocumentSource`, `DocumentVersion`, S3 `put_object` |
| Admin APIs | `api/routers/integrations.py` |
| Admin frontend | `apps/web/app/admin/drive-controls.tsx` |

## Persisted state

Each connection has a `drive_connections` control record and a one-to-one `drive_checkpoints`
record. The checkpoint stores:

- `connection_id` and `tenant_id`;
- `last_change_token`;
- `last_success_time`;
- `next_sync_at`;
- `status`;
- `error_count`;
- `credentials_reference`;
- `last_error`;
- creation/update timestamps.

The API never accepts raw OAuth tokens. `credentials_reference` points to AWS Secrets Manager.
The resolver accepts either an `access_token` for short-lived testing or a production refresh
bundle containing `refresh_token`, `client_id`, and `client_secret`. Refresh bundles are exchanged
against the configurable OAuth token endpoint.

`drive_change_events` provides a second idempotency boundary around each observed file change. It
stores connection, tenant, deterministic change key, file ID, classified action, source version,
status, metadata snapshot, completion time, and last error.

## Configuration

| Field | Default | Meaning |
|---|---:|---|
| `drive.enabled` | `false` | Explicit deployment switch. |
| `sync_interval_seconds` | `300` | Delay after a completed/failed sync. Minimum 30 seconds. |
| `page_size` | `100` | Changes API page size, maximum 1000. |
| `api_base_url` | Google Drive v3 | Metadata/change/download endpoint base. |
| `oauth_token_url` | Google OAuth | Refresh-token exchange endpoint. |
| `secrets_region` | storage region | Secrets Manager region override. |
| `canonical_prefix` | tenant/connection template | Canonical Drive S3 namespace. |
| `include_shared_drives` | `true` | Requests My Drive and shared-drive changes. |
| `allowed_mime_types` | PDF and Google Workspace types | Configurable ingestion allowlist. |
| `export_mime_types` | Docs/Sheets/Slides to PDF | Workspace export mapping. |

Environment example:

```bash
export RAG__DRIVE__ENABLED=true
export RAG__DRIVE__SYNC_INTERVAL_SECONDS=300
export RAG__EVENT_INGESTION__ENABLED=true
export RAG__EVENT_INGESTION__QUEUE_URL='https://sqs.us-east-1.amazonaws.com/123/rag-ingestion'
rag-sync-worker
```

## Initial token behavior

When a connection has no checkpoint token, the worker calls `changes.getStartPageToken`, stores the
returned token, marks the initialization successful, and schedules the next poll. This establishes
incremental synchronization from connection time without repeatedly listing or downloading every
file in the Drive.

An initial historical import is intentionally a separate administrative migration concern. It can
enumerate approved files once and publish them into canonical S3; subsequent mutations then use the
stored Changes token. This separation prevents accidental whole-Drive ingestion when an admin only
intended to connect future changes.

## Incremental polling

1. The scheduler selects active connections whose checkpoint is `IDLE`, `PENDING`, or `FAILED` and
   whose `next_sync_at` is due.
2. The checkpoint becomes `RUNNING`.
3. `changes.list` is called with the stored token, removed items enabled, shared-drive flags, and
   explicit file/permission fields.
4. Every returned change is classified and recorded before external publication.
5. `nextPageToken` is followed until the current change set is exhausted.
6. Only the terminal `newStartPageToken` becomes the durable token for the next scheduled poll.
7. Success stores time/token, clears errors, resets `error_count`, and schedules the next run.
8. Failure retains the old durable token, increments `error_count`, stores the error, and schedules
   a retry. This avoids silently skipping the failed page.

## Change classification

| Drive condition | Platform action |
|---|---|
| `removed=true` or `file.trashed=true` | `DELETE` |
| No existing `DocumentSource` | `CREATE` |
| Parent IDs changed | `MOVE` |
| Permission IDs changed | `PERMISSION_CHANGE` |
| Otherwise | `UPDATE` |

File metadata snapshots retained on `DocumentSource.metadata_json` are used for parent and
permission comparisons. Each Drive file maps uniquely to a tenant/source type/source file ID and
then to one logical platform document.

Files outside `allowed_mime_types` are recorded as `SKIPPED` with an
`UNSUPPORTED_MIME_TYPE` reason. They do not poison the connection checkpoint or queue. Extend the
allowlist only after the shared Phase 1 parser supports the corresponding canonical bytes.

## Create, update, move, and permission flow

For non-delete changes the service:

1. Downloads binary files through `files.get?alt=media`.
2. Exports Google Docs, Sheets, and Slides to configured canonical formats (PDF by default).
3. Computes SHA-256 over the exact canonical bytes.
4. Resolves or creates the tenant-owned logical document and `DocumentSource` mapping.
5. Creates the next immutable platform document version and a `WAITING_EVENT` ingestion job.
6. Creates a deterministic tenant/connection/document/version S3 key.
7. Replaces document ACL rows from the Drive permission snapshot.
8. Uploads with configured server-side encryption and tenant/version/source/checksum metadata.
9. Lets S3 emit the event into EventBridge and SQS.
10. Lets the Phase 9 worker perform the only parsing, chunking, embedding, and indexing path.

Move and permission-only changes update source metadata, filename, and ACLs without creating a
duplicate content version. Content updates publish a new canonical version; an UPDATE whose bytes
match the current document checksum is treated as metadata-only.

## Permission mapping

- Drive `anyone` becomes the tenant principal.
- Drive `group` becomes a platform group principal using email or permission ID.
- Drive `user` email is resolved to an active tenant user ID; unknown users are not granted access.
- Drive `domain` becomes a group principal whose value must be emitted by the identity provider.
- Every imported permission receives the `QUERY` capability only.
- A Drive permission refresh first removes stale document ACL rows, then inserts the new snapshot.
- A delete job removes all document permissions after vector deletion succeeds.

Production identity federation must make Cognito/group claim values match the identifiers selected
for Drive principals. Domain-wide visibility policy should be reviewed before enabling domain
permissions.

## Delete flow

Drive deletion does not create a second deletion implementation:

1. The existing source mapping resolves the logical document and active version.
2. The document is soft-marked `DELETING` with `deleted_at`.
3. A `DELETE` ingestion job targets the active version.
4. A native-shaped `Object Deleted` event with a unique Drive change key is sent to the main SQS
   queue.
5. Phase 9 validates and records the event.
6. The existing processor removes tenant/document-filtered Qdrant vectors.
7. The worker cleans document permissions and marks document/version deleted.
8. SQS is acknowledged only after successful deletion.

The metadata and source mapping are retained for audit and for interpreting later Drive changes.

## Admin API and frontend

All endpoints require the `ADMIN` capability and are tenant scoped:

| Method and path | Control |
|---|---|
| `POST /api/v1/admin/drive/connections` | Connect Drive using display name and secret reference. |
| `GET /api/v1/admin/drive/connections` | View status, token presence, last/next sync, errors. |
| `POST .../{id}/force-sync` | Set `PENDING` and due immediately. |
| `POST .../{id}/pause` | Stop scheduler selection without deleting state. |
| `POST .../{id}/resume` | Reactivate and schedule immediately. |
| `DELETE .../{id}` | Disconnect while preserving audit/history. |
| `GET .../{id}/errors` | View recent per-file failed changes. |

The Next.js administration page exposes Connect, Disconnect, Force Sync, Pause, Resume, last sync,
next sync, cursor initialization, error count, latest error, queue receipt counts, and DLQ alert.
Mutating operations are captured in the tenant audit log without exposing credentials.

## Credentials and IAM

Create one secret per connection or security boundary. Example secret JSON:

```json
{
  "refresh_token": "stored-secret-value",
  "client_id": "google-oauth-client-id",
  "client_secret": "stored-secret-value"
}
```

The sync runtime role needs `secretsmanager:GetSecretValue` only for allowed Drive secret ARNs,
`s3:PutObject` under the canonical Drive prefix, and `sqs:SendMessage` for delete events. The event
worker separately needs S3 read and SQS consume permissions. Do not expose OAuth values through
configuration, database fields, API responses, logs, or browser state.

## Failure and recovery

| Failure | Durable behavior |
|---|---|
| OAuth refresh/secret failure | Checkpoint `FAILED`, counter/error retained, old token retained. |
| Changes page failure | Old terminal checkpoint remains; next run retries. |
| File download/export failure | Change row `FAILED`; checkpoint fails without advancing terminal token. |
| S3 upload failure | No canonical event; change/checkpoint fail and retry. |
| Duplicate change page | Existing change key skips republishing. |
| Duplicate S3 delivery | Phase 9 receipt skips reprocessing. |
| Parse/index failure | Existing active platform version remains selected. |
| Delete/vector failure | No ACK; SQS retries and may DLQ. |

After repeated errors, use the admin errors endpoint to identify the file/action. Fix credentials,
permissions, format, quota, or infrastructure, then Resume or Force Sync. Do not manually advance
the stored change token past failed changes.

## Tests and acceptance

Automated tests cover all five required classifications, event/Drive idempotency boundaries, Drive
admin lifecycle controls, queue health, and the shared SQS worker. Run:

```bash
pytest -q tests/test_phase9_10_events_drive.py
npm --prefix apps/web run build
```

Production acceptance requires a real OAuth client/consent grant, Secrets Manager, Drive test
folder/shared drive, versioned encrypted S3 bucket, EventBridge, SQS/DLQ, PostgreSQL, Qdrant, and
worker roles. Exercise create, content update, move, permission change, trash/delete, duplicate
delivery, forced sync, pause/resume, OAuth failure, and DLQ redrive.

## Exit criteria

- The five-minute default schedule is configurable.
- A durable Changes token is used instead of repeated whole-Drive downloads.
- CREATE, UPDATE, DELETE, MOVE, and PERMISSION CHANGE are classified and recorded.
- All content mutations pass through canonical S3 and the Phase 9 ingestion worker.
- Deletes soft-delete metadata, remove vectors, and clean permissions through the shared lifecycle.
- Admins can connect, disconnect, force, pause, resume, and inspect sync/error state.
- Credentials remain references at rest in application tables and never enter the frontend.
