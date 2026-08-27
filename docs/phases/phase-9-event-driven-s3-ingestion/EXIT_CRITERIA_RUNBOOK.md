# Phase 9 Exit-Criteria Runbook

This runbook records the Phase 9 deployment and acceptance tests for event-driven S3 ingestion.
It extends Phase 8 with S3 EventBridge delivery, SQS, a DLQ, a CloudWatch alarm, and durable
PostgreSQL event receipts.

## 1. Provision AWS infrastructure

Phase 9 uses the existing Phase 8 canonical bucket and EC2 application role. Do not create a
second bucket or instance profile.

```bash
cd terraform/event-ingestion
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

Example `terraform.tfvars`:

```hcl
aws_region       = "ap-south-1"
name             = "replace-with-a-unique-ingestion-name"
bucket_name      = "replace-with-the-phase-8-document-bucket"
bucket_arn       = "arn:aws:s3:::replace-with-the-phase-8-document-bucket"
worker_role_name = "replace-with-the-phase-8-document-app-role"
alarm_actions    = []
```

The Terraform root creates an EventBridge S3 rule limited to `tenants/`, encrypted SQS ingestion
and DLQ queues, a customer-managed KMS key, redrive policy, DLQ CloudWatch alarm, and the worker
S3/SQS/KMS policy attachment.

Capture the raw queue values:

```bash
terraform output -raw queue_url
terraform output -raw dlq_url
```

Use the raw values only. Do not copy Markdown-formatted links into shell commands or YAML files.
The zsh `%` prompt marker is not part of a Terraform output value.

## 2. Configure backend and frontend

Configure `config/rag.yaml`. `RAG__...` environment variables override this file, so start fresh
terminals or remove stale overrides.

```yaml
auth:
  enabled: true
  issuer: https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
  audience: <cognito-app-client-id>
  jwks_cache_seconds: 30

storage:
  bucket: <phase-8-document-bucket>
  region: ap-south-1
  endpoint_url: null
  server_side_encryption: AES256

event_ingestion:
  enabled: true
  queue_url: "https://sqs.<region>.amazonaws.com/<account-id>/<queue-name>"
  dlq_url: "https://sqs.<region>.amazonaws.com/<account-id>/<dlq-name>"
  wait_time_seconds: 20
  visibility_timeout_seconds: 900
  visibility_heartbeat_seconds: 120
  max_messages: 5
  max_receive_count: 5
  accepted_event_types: [Object Created, Object Deleted]
  accepted_prefix: tenants/
  alarm_on_dlq_messages: true
```

The browser configuration stays in `apps/web/.env.local`:

```dotenv
RAG_API_URL=http://127.0.0.1:8080
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_COGNITO_AUTHORIZE_URL=https://<hosted-ui-domain>.auth.<region>.amazoncognito.com/oauth2/authorize
COGNITO_TOKEN_URL=https://<hosted-ui-domain>.auth.<region>.amazoncognito.com/oauth2/token
NEXT_PUBLIC_COGNITO_LOGOUT_URL=https://<hosted-ui-domain>.auth.<region>.amazoncognito.com/logout
NEXT_PUBLIC_COGNITO_CLIENT_ID=<cognito-app-client-id>
```

Restart Next.js after changing `.env.local`.

## 3. Migrate and run services

If Alembic reports multiple heads, inspect and merge the reported revision IDs:

```bash
alembic heads
alembic branches
alembic merge -m "merge migration heads" <head-one> <head-two>
make migrate
```

Run each process separately:

```bash
source .venv/bin/activate
make api
```

```bash
source .venv/bin/activate
make event-worker
```

```bash
source .venv/bin/activate
make ingestion-worker
```

With event ingestion enabled, `make event-worker` owns S3-created upload jobs. The maintenance
worker intentionally claims only `REINDEX` and `DELETE` jobs.

## 4. Validate event-driven upload

Upload a new PDF as a tenant editor or admin. The expected progression is:

```text
PENDING_UPLOAD -> WAITING_EVENT -> RECEIVED -> parsing/chunking/embedding/indexing -> ACTIVE
```

Verify the receipt and job:

```bash
docker compose exec -T postgres psql -U rag -d rag_platform -c "
SELECT r.provider, r.event_id, r.event_type, r.object_key, r.status,
       r.receive_count, r.last_error, j.status AS job_status, j.stage
FROM ingestion_receipts r
JOIN ingestion_jobs j ON j.id = r.ingestion_job_id
ORDER BY r.created_at DESC
LIMIT 5;
"
```

Expected: `PROCESSED` receipt, `receive_count = 1`, and job `SUCCEEDED / ACTIVE`.

## 5. Validate idempotency and maintenance jobs

1. Re-send a completed EventBridge-style event with the same `event_id` directly to SQS.
   The worker must acknowledge it without creating another ingestion job.
2. Select **Reindex** on an active document. Its `REINDEX` job must become `SUCCEEDED / ACTIVE`.
3. Upload and index a disposable PDF, select **Delete**, and confirm its `DELETE` job becomes
   `SUCCEEDED / DELETED`.

```bash
docker compose exec -T postgres psql -U rag -d rag_platform -c "
SELECT id, job_type, status, stage, attempts, error_message
FROM ingestion_jobs
ORDER BY created_at DESC
LIMIT 10;
"
```

## 6. Validate the DLQ and alarm

For a short test, temporarily set the event-worker visibility timeout to `30` and heartbeat to
`10` seconds, then restart the event worker. Send an invalid queue message. The worker must reject
it and leave it unacknowledged. After five receives, SQS moves it to the DLQ.

```bash
aws sqs get-queue-attributes \
  --region <region> \
  --queue-url "$(terraform -chdir=terraform/event-ingestion output -raw dlq_url)" \
  --attribute-names ApproximateNumberOfMessages
```

Expected: `ApproximateNumberOfMessages = 1`. Confirm the Phase 9 CloudWatch alarm reaches
`ALARM`. Restore production values (`visibility_timeout_seconds: 900` and
`visibility_heartbeat_seconds: 120`) and restart the event worker.

## Troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `QueueDoesNotExist` | Malformed queue URL or wrong SQS region. | Use raw Terraform output and set `storage.region` to the queue region. |
| `KMS.AccessDenied` on `ReceiveMessage` | Worker role lacks KMS decrypt access. | Apply the Terraform policy granting `kms:Decrypt` and `kms:GenerateDataKey` on the queue key. |
| Browser S3 POST returns `307` | Presigned POST used the global S3 endpoint. | Deploy the regional S3 endpoint fix and restart the API. |
| Job remains `WAITING_EVENT` | Event did not arrive or the event worker is stopped. | Check bucket EventBridge notification, rule target, queue metrics, and worker logs. |
| Cognito redirects to placeholders | Frontend `.env.local` has old values. | Update Hosted UI URLs and restart Next.js. |

## Exit evidence

- [x] A new S3 upload produced a `PROCESSED` receipt and `SUCCEEDED / ACTIVE` job.
- [x] Duplicate event delivery did not create another ingestion job.
- [x] Reindex and delete maintenance jobs completed.
- [x] An invalid queue message retried and entered the DLQ.
- [x] The DLQ CloudWatch alarm reached `ALARM` with one visible message.
