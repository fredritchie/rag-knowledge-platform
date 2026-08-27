# Terraform

## Phase 7 Cognito test environment

[`cognito/`](./cognito) provisions the Amazon Cognito resources needed to validate
Phase 7 authentication: a user pool, browser app client, hosted UI domain, custom
tenant/group attributes, optional test users, and Admin/Editor/Viewer groups.

It does not manage user passwords. That prevents credentials from entering source
control or Terraform state.

```bash
cd terraform/cognito
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

Use the outputs to configure the API:

```bash
terraform output -raw issuer
terraform output -raw app_client_id
terraform output -raw hosted_ui_base_url
```

Set the first two values as `RAG__AUTH__ISSUER` and `RAG__AUTH__AUDIENCE`. Use the
hosted UI base URL to populate the frontend Cognito authorize, token, and logout
environment variables. The configured app client intentionally has no secret so it
can be used by the browser authorization-code flow with PKCE.

Create active PostgreSQL `users` and `tenant_memberships` records matching each
Cognito subject and `custom:tenant_id`; application authorization is based on those
membership records. Destroy the isolated test environment when the test is complete:

```bash
terraform destroy
```
