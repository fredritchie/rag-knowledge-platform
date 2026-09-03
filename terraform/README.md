# AWS infrastructure

Phase 13 adds the production AWS foundation while retaining the earlier phase-specific examples under `event-ingestion/` and `drive-sync/`.

The reusable modules cover VPC networking, IAM and identity, ECR, S3, SQS/DLQ, Aurora PostgreSQL, EKS, ALB/Route53/ACM/WAF, and CloudWatch/SNS. `modules/platform` only composes those focused modules so dev, staging, and prod keep identical topology.

Only the ALB accepts internet ingress. EKS nodes, Qdrant and GPU pools, and Aurora use private subnets without public IPs; the EKS API endpoint is private-only.

## Initialize state

Apply `bootstrap/` once with local state. Copy its outputs into each environment's ignored `backend.hcl` and input file:

```bash
cd terraform/environments/dev
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
terraform apply tfplan
```

Each environment has a distinct S3 object key. The backend uses KMS encryption, bucket versioning, and S3 native lockfiles.

The ALB target group ARN is an output for the next deployment phase to bind to a private Kubernetes service.

## Drift detection

`.github/workflows/terraform-drift.yml` runs nightly for all environments. Exit code `0` means clean, `2` uploads the plan and raises a GitHub issue plus SNS alert, and `1` uploads diagnostics and fails. The workflow never applies or repairs drift.

Configure GitHub environments named `dev`, `staging`, and `prod`. Each needs a `TERRAFORM_TFVARS` environment secret and these environment variables: `AWS_REGION`, `AWS_TERRAFORM_DRIFT_ROLE_ARN`, `TF_STATE_BUCKET`, `TF_STATE_KMS_KEY_ARN`, and `TERRAFORM_DRIFT_SNS_TOPIC_ARN`.
