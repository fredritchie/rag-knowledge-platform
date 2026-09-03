# Phase 13: AWS infrastructure with Terraform

The platform now has a reusable, three-AZ AWS foundation for dev, staging, and production. Public subnets contain only the internet-facing ALB and NAT gateways. Application, Qdrant, GPU, and PostgreSQL capacity stays private.

Provisioned services include VPC networking and encrypted flow logs; private EKS general, Qdrant, and GPU pools; ALB, ACM, Route53, and WAF; encrypted S3, SQS/DLQ, Aurora, and ECR; Cognito and Secrets Manager; and CloudWatch/SNS monitoring.

Terraform creates the ALB target group but does not register public node targets. A later Kubernetes/GitOps phase must deploy workloads and bind private services. Runtime secret values are populated outside Terraform so plaintext values never enter state.

State locking uses Terraform's S3 lockfile support. The bootstrap root is separate because a backend cannot create itself. Drift is reported through a plan artifact, GitHub issue, and SNS, and is never repaired automatically.

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
- The EKS API endpoint is private, and the general, Qdrant, and GPU managed node groups successfully register with the cluster and report `Ready`.
- Qdrant and GPU nodes have their dedicated labels and `NoSchedule` taints. Deploying the Qdrant StatefulSet itself belongs to the subsequent Kubernetes/GitOps phase.
- Aurora PostgreSQL is reachable from approved Kubernetes workloads but not from the internet. Encryption, IAM database authentication, backups, enhanced monitoring, log export, and Secrets Manager-managed credentials are enabled.
- The canonical S3 bucket is private, versioned, and KMS-encrypted. Object events under `tenants/` reach the encrypted ingestion queue, and exhausted retries reach the DLQ.
- All expected immutable ECR repositories exist with push scanning and lifecycle retention enabled.
- Cognito, the runtime Secrets Manager container, CloudWatch logs and alarms, and the SNS alert topic are provisioned.

### Public edge and operations

- Route53 resolves the application hostname to the public ALB, and the ACM certificate validates successfully.
- HTTPS reaches the ALB through WAF; no Kubernetes node, Qdrant endpoint, GPU node, or database endpoint is directly internet-accessible.
- The WAF managed-rule groups, rate limit, request logging, and ALB access logging are active.
- A reviewed `terraform plan` succeeds for every environment before deployment.
- At least the dev environment has been applied and smoke-tested in AWS, including HTTPS, node registration, database connectivity, S3-to-SQS delivery, DLQ behavior, and alarm delivery.
- The nightly drift workflow demonstrates all three outcomes: `0` reports no drift, `2` uploads a plan and creates a GitHub issue plus SNS alert, and `1` uploads diagnostics and fails the job.
- The drift workflow contains no `terraform apply` or automatic repair path.

Repository validation alone is not operational sign-off. AWS deployment and the dev smoke test are required before Phase 13 can be marked complete.
