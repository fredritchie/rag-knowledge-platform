# Phase 9 — Event-Driven S3 Ingestion

For the complete EC2/Terraform deployment, validation, and troubleshooting procedure, see the
[Phase 9 exit-criteria runbook](EXIT_CRITERIA_RUNBOOK.md).

## Outcome

Phase 9 replaces the upload-complete request as the source of truth with a durable S3 event path:

```text
canonical S3 bucket
  -> Amazon EventBridge rule
  -> encrypted Amazon SQS queue
  -> rag-s3-event-worker
  -> existing parse/chunk/embed/index lifecycle
  -> PostgreSQL activation transaction
  -> SQS acknowledgement

processing failure -> visibility timeout -> retry -> DLQ -> CloudWatch alarm
```

The HTTP upload-complete endpoint remains compatible with Phase 8, but deployments using Phase 9
should treat the S3 `Object Created` event as authoritative. The event worker only deletes an SQS
message after the database job reaches `SUCCEEDED`. A crash, timeout, parser error, checksum error,
or index error leaves the message unacknowledged so SQS can redeliver it.

## Source map

| Concern | Implementation |
|---|---|
| EventBridge envelope validation | `src/rag_platform/workers/s3_events.py::StorageEvent` |
| Long-polling, ACK, visibility operations | `SQSQueueClient` |
| Durable inbox and idempotency | `IngestionReceipt` in `application/db/models.py` |
| Queue-to-job orchestration | `S3EventWorker` |
| S3 download/checksum/pipeline | `S3PipelineProcessor` |
| Existing activation transaction | `workers/ingestion.py::IngestionWorker` |
| Schema migration | `migrations/versions/20260823_0002_event_and_drive_state.py` |
| AWS resources and IAM | `terraform/modules/event_ingestion` |
| Queue/DLQ admin health | `GET /api/v1/admin/ingestion/queue-health` |

## Configuration

All fields can be set in `config/rag.yaml` or as `RAG__EVENT_INGESTION__...` environment values.

| Field | Default | Purpose |
|---|---:|---|
| `enabled` | `false` | Prevents accidental queue consumption in local development. |
| `queue_url` | empty | Main SQS queue URL. Required by the event worker. |
| `dlq_url` | empty | DLQ URL used by the admin health endpoint. |
| `wait_time_seconds` | `20` | SQS long-poll duration. |
| `visibility_timeout_seconds` | `900` | Initial and renewed processing lease. |
| `visibility_heartbeat_seconds` | `120` | Interval used to renew the SQS processing lease. |
| `max_messages` | `5` | Maximum SQS receive batch, constrained to 1–10. |
| `max_receive_count` | `5` | Expected Terraform redrive count and operator reference. |
| `accepted_event_types` | create/delete | Explicit event allowlist. |
| `accepted_prefix` | `tenants/` | Rejects events outside the canonical object namespace. |
| `alarm_on_dlq_messages` | `true` | Documents that any visible DLQ message is alertable. |

The S3 bucket name, region, endpoint, encryption mode, and optional KMS key remain under `storage`.
Queue and bucket configuration must agree with the Terraform module outputs.

Example:

```bash
export RAG__EVENT_INGESTION__ENABLED=true
export RAG__EVENT_INGESTION__QUEUE_URL='https://sqs.us-east-1.amazonaws.com/123/rag-ingestion'
export RAG__EVENT_INGESTION__DLQ_URL='https://sqs.us-east-1.amazonaws.com/123/rag-ingestion-dlq'
export RAG__STORAGE__BUCKET='company-rag-canonical'
rag-s3-event-worker
```

## Exact message contract

The parser accepts the native S3 EventBridge envelope. Required values are:

- `source` exactly `aws.s3`;
- top-level `id`, used as the provider event ID;
- `detail-type`, restricted by configuration;
- `detail.bucket.name`, which must match the canonical bucket;
- `detail.object.key`, decoded and matched to the configured prefix;
- optional `detail.object.version-id`; `unversioned` is stored when absent;
- optional top-level event time.

The object key must already belong to a `document_versions.storage_key`. Random objects cannot
create documents implicitly. This prevents an event in a shared or incorrectly filtered bucket
from bypassing tenant ownership and document authorization.

## Processing sequence

1. SQS long polling returns the body, message ID, receipt handle, and approximate receive count.
2. `StorageEvent` parses and structurally validates the EventBridge envelope.
3. The worker validates event type, bucket name, and object prefix.
4. PostgreSQL is queried for an existing receipt with the same provider/event ID.
5. If it is already `PROCESSED`, the duplicate is acknowledged immediately.
6. The canonical object key is resolved to one platform document version and its ingestion job.
7. A receipt is inserted before processing. Database uniqueness also protects concurrent workers.
8. The S3 object version is stored on the platform document version.
9. The job becomes `RUNNING`, and its attempt count is incremented.
10. A background heartbeat renews message visibility while the processor is running.
11. The processor downloads that exact object/object version to an isolated temporary directory.
12. SHA-256 is recalculated and compared with the checksum authorized or created upstream.
13. The existing Phase 1 parser performs PDF validation, extraction, quality checks, and chunking.
14. The existing Phase 2 retrieval service embeds and indexes the chunks in Qdrant.
15. The processor verifies that at least one chunk exists and indexed count equals chunk count.
16. The application worker activates the new PostgreSQL version only after successful validation.
17. The receipt becomes `PROCESSED` with `processed_at`.
18. Only then is `DeleteMessage` sent to SQS.

## Idempotency model

`ingestion_receipts` stores all three required identities:

- provider `event_id`;
- S3 `object_version` plus bucket/key/event type;
- platform `document_version_id`.

There are two database unique constraints. `(provider, event_id)` handles repeated delivery of the
same EventBridge envelope. `(provider, bucket, object_key, object_version, event_type)` handles
separate envelopes describing the same versioned storage mutation. Both paths return the existing
receipt rather than starting another parse/index cycle.

Receipt states are `RECEIVED`, `RETRYING`, and `PROCESSED`. `receive_count`, SQS message ID,
ingestion job ID, last error, creation/update timestamps, and completion time are retained for
operations and incident analysis.

## Retry and DLQ behavior

Application code does not manually move messages to the DLQ. The main queue redrive policy does
that after `maxReceiveCount`. This preserves SQS as the authority for receive attempts and avoids
double-publishing poison messages.

The Terraform module creates:

- an encrypted main queue with 20-second long polling;
- an encrypted DLQ with a longer retention period;
- the source-queue redrive policy and DLQ allow policy;
- an EventBridge rule filtered to the canonical bucket and prefix;
- the EventBridge-to-SQS resource policy;
- S3 EventBridge notification enablement;
- a CloudWatch alarm when visible DLQ messages are at least one;
- a worker IAM policy for queue receive/ACK/visibility/send and versioned S3 access.

Set `alarm_actions` to an SNS topic or supported CloudWatch action. A green application health
check does not suppress the DLQ alarm: one poison document is operationally significant even when
the API and other documents remain healthy.

## Failure classification

| Failure | Result |
|---|---|
| Invalid JSON/envelope | No ACK; retries and eventually reaches DLQ. |
| Wrong bucket/prefix/type | No ACK; indicates infrastructure routing drift. |
| Unknown object key | No ACK; prevents unauthorized implicit ingestion. |
| Duplicate completed event | Immediate ACK with no parsing. |
| Checksum mismatch | Job and receipt record failure; no ACK. |
| PDF/quality rejection | Existing classified ingestion error; no ACK. |
| Embedding/Qdrant failure | Existing active version remains selected; no ACK. |
| Worker crash | SQS visibility expires and another worker can receive. |
| Database commit before ACK then crash | Redelivery sees `PROCESSED` and ACKs without processing. |

## Deployment

Instantiate `terraform/modules/event_ingestion` with the existing canonical bucket. Attach its
`worker_policy_arn` output to the worker role. If another Terraform resource already owns the S3
bucket notification configuration, enable EventBridge in that owner rather than defining two
notification resources.

Run migrations before starting consumers:

```bash
alembic upgrade head
rag-s3-event-worker
```

Scale workers horizontally. PostgreSQL uniqueness and SQS receipt handles provide concurrency
safety; each process has an independent long poll. Set queue visibility higher than the longest
accepted PDF processing duration. The worker renews visibility at the configured heartbeat until
the processor completes.

## Operations

Admin queue status:

```http
GET /api/v1/admin/ingestion/queue-health
Authorization: Bearer <admin-token>
```

The response includes feature enablement, DLQ visible-message count when a queue client is attached
to the API process, an `alert` boolean, and tenant-scoped receipt counts. CloudWatch remains the
primary production DLQ alarm because it does not depend on API availability.

For a DLQ incident:

1. Inspect the receipt, job, and ingestion event using event/object/document version IDs.
2. Correct data, configuration, permissions, or an application defect.
3. Redrive through the main queue; do not publish directly to the worker.
4. Confirm receipt/job success, queue drain, vector availability, and alarm recovery.
5. Retain the original event and incident evidence for audit.

## Tests and acceptance

`tests/test_phase9_10_events_drive.py` covers EventBridge parsing, persisted identifiers, duplicate
delivery, exactly-once processing effect, ACK behavior, and admin health/control endpoints. Run:

```bash
pytest -q tests/test_phase9_10_events_drive.py
```

Production acceptance additionally requires a real versioned S3 bucket, EventBridge rule, main
queue, DLQ, PostgreSQL, Qdrant, runtime IAM role, and alarm action. Inject a deliberately invalid
PDF, confirm retries and DLQ delivery, then redrive after correcting the cause.

## Exit criteria

- S3 create and Drive delete events enter SQS through the intended route.
- Duplicate delivery does not repeat parsing/indexing.
- Checksums are verified after download.
- Activation occurs only after parsing, quality, chunk, embed, index, and validation success.
- Failed replacement ingestion preserves the previously active version.
- Successful events are acknowledged only after database success.
- Poison messages reach the DLQ and trigger an alarm at one visible message.
