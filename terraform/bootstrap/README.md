# Remote-state bootstrap

This root is intentionally applied with local state. It creates the versioned, private S3 state
bucket and customer-managed KMS key. It can create the account-level GitHub Actions OIDC provider
or reuse its ARN when one already exists. It also creates a Terraform deployment role whose trust is
restricted to the configured protected GitHub environment. PowerUserAccess provisions AWS resources;
the supplemental IAM policy can manage only roles and policies under
`terraform_managed_name_prefix`, which must not include the deployment role itself. Isolated
staging and prod roles are created by default with access only to their matching resource prefixes.

```bash
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
terraform output -raw backend_hcl_template
terraform output -json terraform_deploy_role_arns
```

Copy the output into each environment's untracked `backend.hcl`, add that environment's unique `key`, then initialize with `terraform init -backend-config=backend.hcl`. S3 native lockfiles (`use_lockfile = true`) provide state locking without a DynamoDB table.

Set each role ARN as the `AWS_TERRAFORM_ROLE_ARN` secret on its matching GitHub environment. The
trust targets use the customized repository subject and exact environment name; change
`github_oidc_subject_prefix` only if the repository's GitHub OIDC subject customization changes.
