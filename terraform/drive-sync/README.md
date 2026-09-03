# Phase 10 Drive Sync Infrastructure

This root creates an empty AWS Secrets Manager secret encrypted by a customer-managed KMS key and
attaches the Drive sync policy to the existing Phase 8/9 EC2 worker role. The policy can read only that secret, write canonical Drive
objects under `tenants/*/drive/*`, publish delete events to the Phase 9 queue, and use the queue
KMS key.

OAuth tokens are not Terraform variables and are never stored in Terraform state or the repository.

## OAuth rotation exception

Google OAuth refresh-token bundles cannot be safely rotated by a generic AWS Lambda: rotating the
Google OAuth client secret requires an approved Google Cloud workflow and a re-consent or credential
handoff process. The secret therefore has a documented Checkov exception for automatic rotation,
which expires on 2026-12-01. Before that date, either implement the approved Google-side rotation
workflow or renew the exception after security review.

## Apply

```bash
cd terraform/drive-sync
cp terraform.tfvars.example terraform.tfvars
# Fill in existing bucket, queue, KMS key, role, and desired secret names.
terraform init
terraform plan
terraform apply
```

After applying, store the Google OAuth refresh-token bundle in the created secret using AWS Console,
CloudShell, or AWS CLI. Use the `google_oauth_secret_arn` output as the Drive connection
`credentials_reference` in the tenant admin API or UI.
