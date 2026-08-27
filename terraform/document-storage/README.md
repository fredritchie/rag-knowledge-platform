# Phase 8 document storage

This module creates the private canonical S3 document bucket and IAM permissions
for the API and ingestion worker. It provides:

- bucket-owner-enforced object ownership and all public-access blocks;
- AES256 default server-side encryption and versioning;
- browser CORS for direct presigned `POST` uploads;
- an EC2 application role restricted to `tenants/*` objects; and
- an instance profile to attach to the existing EC2 application instance.

## Provision

```bash
cd terraform/document-storage
cp terraform.tfvars.example terraform.tfvars
# Edit the bucket name and allowed browser origins.
terraform init
terraform plan
terraform apply
```

Use the outputs to configure the API process:

```bash
export RAG__STORAGE__BUCKET="$(terraform output -raw bucket_name)"
export RAG__STORAGE__REGION="$(terraform output -raw storage_region)"
export RAG__STORAGE__SERVER_SIDE_ENCRYPTION="$(terraform output -raw server_side_encryption)"
```

Attach the `instance_profile_name` output to the EC2 instance before starting
the API. The SDK then obtains temporary credentials through the instance
metadata service; do not set long-lived AWS access keys in application
environment variables.

The `app_origins` value must include every browser origin that uploads directly
to S3. For a public application Cognito requires an HTTPS domain; retain the
localhost origin only for the SSH-tunnel development flow.

The module grants storage access only. A concrete Phase 8 ingestion/deletion
processor must still be supplied to download, parse, chunk, embed, validate,
index, and delete document versions.
