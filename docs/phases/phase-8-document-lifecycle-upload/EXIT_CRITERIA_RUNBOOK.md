# Phase 8 Exit-Criteria Runbook

This runbook records the manual-upload, ingestion, lifecycle, and tenant-isolation verification
performed for Phase 8. It assumes Phase 7 Cognito authentication and tenant memberships already
work.

## 1. Provision document storage

Create the S3 bucket and EC2 application role with Terraform:

```bash
cd terraform/document-storage
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

Set a globally unique `bucket_name` and allow the browser origin used by the SSH tunnel:

```hcl
aws_region  = "ap-south-1"
bucket_name = "replace-with-a-globally-unique-bucket"
app_origins = ["http://localhost:3000"]
```

Attach the Terraform-created instance profile to the EC2 instance. Verify from EC2:

```bash
aws sts get-caller-identity
```

The identity must be the document application role. Do not put AWS access keys in configuration
files; the EC2 instance profile supplies them.

## 2. Configure the API and worker

Set stable backend settings in `config/rag.yaml` on EC2:

```yaml
auth:
  enabled: true
  issuer: https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
  audience: <cognito-app-client-id>
  jwks_cache_seconds: 30

storage:
  provider: s3
  bucket: <document-bucket>
  region: ap-south-1
  endpoint_url: null
  upload_expiry_seconds: 900
  server_side_encryption: AES256
  kms_key_id: null

qdrant:
  url: http://localhost:6333
  collection: rag_chunks

worker:
  poll_interval_seconds: 2
  batch_size: 5
  max_attempts: 3
```

Environment variables beginning with `RAG__` override this file. Start fresh terminals or unset old
overrides before testing the file configuration.

Install ML dependencies and start the API and worker in separate terminals:

```bash
cd ~/rag-knowledge-platform
source .venv/bin/activate
make install-ml
make migrate
make api
```

```bash
cd ~/rag-knowledge-platform
source .venv/bin/activate
make ingestion-worker
```

The worker downloads the S3 object, verifies SHA-256, extracts PDF text with PyMuPDF, chunks it,
embeds chunks with the configured model, writes tenant-scoped vectors to Qdrant, then activates the
document version.

## 3. Configure the browser application

Use an SSH tunnel from the development machine:

```bash
ssh -L 3000:127.0.0.1:3000 -i <key-file> ubuntu@<ec2-public-ip>
```

In `apps/web/.env.local` on EC2, configure the frontend separately from `config/rag.yaml`:

```dotenv
RAG_API_URL=http://127.0.0.1:8080
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_COGNITO_AUTHORIZE_URL=https://<domain>.auth.ap-south-1.amazoncognito.com/oauth2/authorize
COGNITO_TOKEN_URL=https://<domain>.auth.ap-south-1.amazoncognito.com/oauth2/token
NEXT_PUBLIC_COGNITO_LOGOUT_URL=https://<domain>.auth.ap-south-1.amazoncognito.com/logout
NEXT_PUBLIC_COGNITO_CLIENT_ID=<cognito-app-client-id>
```

Start it in another terminal:

```bash
cd ~/rag-knowledge-platform/apps/web
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://localhost:3000`, authenticate as a Tenant A editor or admin, and navigate to
`/documents`.

## 4. Upload and process a PDF

Upload a small text-based PDF. The expected sequence is:

```text
Browser calculates SHA-256
  -> API authorizes tenant-scoped presigned POST
  -> browser uploads directly to regional S3 endpoint
  -> browser acknowledges upload completion
  -> job is QUEUED
  -> worker indexes chunks in Qdrant
  -> job and document version become ACTIVE/SUCCEEDED
```

Check jobs:

```bash
docker compose exec -T postgres psql -U rag -d rag_platform -c "
SELECT id, job_type, status, stage, progress_percent, attempts, error_message
FROM ingestion_jobs
ORDER BY created_at DESC
LIMIT 10;
"
```

Check the activated document and version:

```bash
docker compose exec -T postgres psql -U rag -d rag_platform -c "
SELECT d.filename, d.status AS document_status, v.status AS version_status,
       v.page_count, v.chunk_count, v.embedding_version
FROM documents d
JOIN document_versions v ON v.id = d.current_version_id
ORDER BY d.updated_at DESC
LIMIT 5;
"
```

Check that Qdrant contains vectors:

```bash
curl -s http://127.0.0.1:6333/collections/rag_chunks | jq
```

## 5. Validate lifecycle controls

1. Upload the same PDF again. Expect `DUPLICATE_DOCUMENT` and no new ingestion job.
2. On an active document detail page, select **Reindex**. Expect a `REINDEX` job to reach
   `SUCCEEDED`.
3. Upload a disposable document, allow it to index, then select **Delete**. Expect a `DELETE` job
   to reach `SUCCEEDED` with `stage = DELETED`:

```bash
docker compose exec -T postgres psql -U rag -d rag_platform -c "
SELECT id, job_type, status, stage, error_message
FROM ingestion_jobs
WHERE job_type = 'DELETE'
ORDER BY created_at DESC
LIMIT 3;
"
```

4. Sign in as Tenant B. Tenant B must not list or access Tenant A documents; repeat the converse
   check from Tenant A.

## 6. Troubleshooting observed during validation

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Browser S3 POST returned `307` and CORS error | A global S3 endpoint redirected to the bucket's region. | Deploy the regional-endpoint fix; presigned URL must be `https://<bucket>.s3.<region>.amazonaws.com/`. |
| JWT verification requested `replace-me` | API Cognito issuer was still the default. | Set the real `auth.issuer` and `auth.audience` in `config/rag.yaml`, then restart the API. |
| Hosted UI opened `replace-me` | Next.js `.env.local` still held placeholder authorize/token/logout URLs. | Update all Cognito frontend URLs and restart Next.js. |
| Job failed with `No production document processor is configured` | The old placeholder worker ran. | Deploy the S3/Qdrant worker, then explicitly requeue only that failed job. |
| Job failed with S3 `HeadObject 404` | The browser upload never reached S3. | Do not requeue; remove only the failed object-less attempt after checking it has no active version, then upload again. |

## Exit evidence

Record the following before closing Phase 8:

- An upload job reached `SUCCEEDED / ACTIVE`.
- The active version has non-zero page and chunk counts.
- Qdrant has points for the indexed document.
- Duplicate upload was rejected.
- Reindex job succeeded.
- Delete job succeeded with `DELETED`.
- Tenant A and Tenant B cannot access each other's documents.
