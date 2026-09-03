# Remote-state bootstrap

This root is intentionally applied once with local state. It creates the versioned, private S3 state bucket and customer-managed KMS key. It can create the account-level GitHub Actions OIDC provider or reuse its ARN when one already exists.

```bash
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
terraform output -raw backend_hcl_template
```

Copy the output into each environment's untracked `backend.hcl`, add that environment's unique `key`, then initialize with `terraform init -backend-config=backend.hcl`. S3 native lockfiles (`use_lockfile = true`) provide state locking without a DynamoDB table.
