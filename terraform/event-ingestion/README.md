# Phase 9 Event-Driven Ingestion Infrastructure

This root configuration attaches the reusable event-ingestion module to the Phase 8 document
bucket and EC2 application role. It creates a customer-managed KMS key, encrypted SQS ingestion
queue and DLQ, EventBridge rule/target, S3 EventBridge notification, DLQ CloudWatch alarm, and the
least-privilege worker policy attachment.

The Phase 8 `document-storage` root remains the owner of bucket versioning and the EC2 instance
profile. Do not create a second S3 versioning resource here.

## Apply

```bash
cd terraform/event-ingestion
cp terraform.tfvars.example terraform.tfvars
# Fill in the existing Phase 8 bucket name/ARN and document application role name.
terraform init
terraform plan
terraform apply
```

After apply, copy the `queue_url` and `dlq_url` outputs into `config/rag.yaml` under
`event_ingestion`, set `enabled: true`, and start `make event-worker`.

Only one Terraform resource may manage S3 bucket notifications. The Phase 8 document-storage
configuration does not manage one; if another stack begins to do so, move `eventbridge = true`
there before applying this root.
