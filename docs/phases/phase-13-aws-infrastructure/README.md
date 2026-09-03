# Phase 13: AWS infrastructure with Terraform

The platform now has a reusable, three-AZ AWS foundation for dev, staging, and production. Public subnets contain only the internet-facing ALB and NAT gateways. Application, Qdrant, GPU, and PostgreSQL capacity stays private.

Provisioned services include VPC networking and encrypted flow logs; private EKS general, Qdrant, and GPU pools; ALB and WAF with optional ACM/Route53 DNS; encrypted S3, SQS/DLQ, Aurora, and ECR; Cognito and Secrets Manager; and CloudWatch/SNS monitoring.

Terraform creates the ALB target group but does not register public node targets. A later Kubernetes/GitOps phase must deploy workloads and bind private services. Runtime secret values are populated outside Terraform so plaintext values never enter state.

State locking uses Terraform's S3 lockfile support. The bootstrap root is separate because a backend cannot create itself. Drift is reported through a plan artifact, GitHub issue, and SNS, and is never repaired automatically.

Nightly drift detection includes only applied environments. Dev is enabled now; staging and
production must be added to the workflow matrix only after their GitHub environment inputs are
configured and their first reviewed apply has completed.

Dev is intentionally domainless: `enable_https = false` exposes the WAF-associated ALB listener on
HTTP and reports the generated ALB hostname. This is suitable only for infrastructure smoke tests.
Staging and production must use HTTPS with a DNS zone capable of creating ACM validation CNAMEs and
an alias or CNAME to the ALB. DuckDNS supports A/AAAA and TXT updates but not those required CNAME or
alias records, so it cannot satisfy the production ACM/ALB exit criterion by itself.

## Teardown and cost shutdown

Destroy an application environment before destroying its state backend. For dev, keep
`deletion_protection = false`; this also permits Terraform to empty the dev document and ALB-log
buckets and delete non-empty ECR repositories. Staging and production default to protection and
must be deliberately changed to `false` and applied before they can be destroyed.

First remove Kubernetes-managed load balancers, persistent volumes, and other AWS resources created
outside this Terraform state. Then review and apply a saved destroy plan:

```bash
terraform -chdir=terraform/environments/dev init -reconfigure -backend-config=backend.hcl
terraform -chdir=terraform/environments/dev plan -destroy -var-file=terraform.tfvars -out=destroy.tfplan
terraform -chdir=terraform/environments/dev show destroy.tfplan
terraform -chdir=terraform/environments/dev apply destroy.tfplan
```

Repeat for staging and production only when those environments are intentionally being retired.
KMS key deletion is scheduled with a 30-day recovery window, so keys remain visible but unusable
until AWS completes deletion.

The bootstrap state bucket has `prevent_destroy = true` and is retained by design. To decommission
the account completely, first destroy every environment, preserve an offline copy of all state
versions, then use a separately reviewed break-glass change to remove that lifecycle protection and
empty the versioned bucket before destroying the bootstrap root. Never destroy the bootstrap first:
doing so removes the state and lock data needed for an orderly environment teardown.

## Exit criteria

Phase 13 is complete only when all of the following criteria are satisfied.

### Repository and Terraform validation

- `terraform fmt -check -recursive terraform` succeeds.
- `terraform validate` succeeds for `bootstrap`, `dev`, `staging`, and `prod`.
- Terraform security scanning reports no unreviewed failed checks.
- Dev, staging, and production use distinct remote-state object keys.
- The remote-state bucket has versioning, customer-managed KMS encryption, public-access blocking, and S3 native state locking enabled.
- No credentials or runtime secret values are committed or written into Terraform state deliberately.

### AWS infrastructure

- The VPC spans three availability zones with one public and one private subnet in each zone.
- Public route tables expose only the ALB and NAT path; EKS nodes and Aurora instances have no public IP addresses.
- The EKS API endpoint is private. The general and Qdrant managed-node instances register with the cluster and report `Ready`; the GPU node group is `ACTIVE`, has the expected join configuration, and may remain at desired size zero in cost-controlled environments.
- Qdrant and GPU nodes have their dedicated labels and `NoSchedule` taints. Deploying the Qdrant StatefulSet itself belongs to the subsequent Kubernetes/GitOps phase.
- Aurora PostgreSQL is reachable from approved Kubernetes workloads but not from the internet. Encryption, IAM database authentication, backups, enhanced monitoring, log export, and Secrets Manager-managed credentials are enabled.
- The canonical S3 bucket is private, versioned, and KMS-encrypted. Object events under `tenants/` reach the encrypted ingestion queue, and exhausted retries reach the DLQ.
- All expected immutable ECR repositories exist with push scanning and lifecycle retention enabled.
- Cognito, the runtime Secrets Manager container, CloudWatch logs and alarms, and the SNS alert topic are provisioned.

### Public edge and operations

- For HTTPS environments, Route53 resolves the application hostname to the public ALB and the ACM certificate validates successfully. Domainless dev resolves through the generated ALB hostname.
- HTTP(S) reaches the ALB through WAF according to the environment's edge configuration; no Kubernetes node, Qdrant endpoint, GPU node, or database endpoint is directly internet-accessible.
- The WAF managed-rule groups, rate limit, request logging, and ALB access logging are active.
- A reviewed `terraform plan` succeeds for every environment before deployment.
- At least the dev environment has been applied and smoke-tested in AWS, including its WAF-protected ALB endpoint, node registration, database connectivity, S3-to-SQS delivery, DLQ behavior, and alarm delivery. HTTPS is mandatory before production sign-off.
- The nightly drift workflow demonstrates all three outcomes: `0` reports no drift, `2` uploads a plan and creates a GitHub issue plus SNS alert, and `1` uploads diagnostics and fails the job.
- The drift workflow contains no `terraform apply` or automatic repair path.

Repository validation alone is not operational sign-off. AWS deployment and the dev smoke test are required before Phase 13 can be marked complete.
