# Application deployment runbook

The EKS API endpoint remains private. GitHub Actions starts a least-privilege CodeBuild project
attached to the environment's private subnets; Helm and kubectl never connect from a public runner.

## One-time infrastructure update

After this change reaches `main`, run `terraform-environment-deployment` for the target environment:

1. Dispatch `plan` and review the saved plan artifact.
2. Dispatch `apply` with the successful plan run ID.
3. Copy Terraform outputs into the protected GitHub environment:
   - secret `AWS_APPLICATION_DEPLOY_ROLE_ARN` from `application_deploy_role_arn`;
   - variable `AWS_APPLICATION_DEPLOY_PROJECT` from `application_deploy_project_name`.

The infrastructure update creates a private CodeBuild deployment project, a narrowly scoped GitHub
OIDC trigger role, an EKS access entry, application Pod Identity permissions, a Cognito hosted UI
domain, and an empty Grafana credential container. The first platform deployment generates a random
Grafana password and stores it in that encrypted Secrets Manager container without placing it in
Terraform state or GitHub.

## Image promotion

Merges to `main` run `container-supply-chain`. It tests and scans all project images, generates
SBOMs, pushes immutable revisions to ECR, signs image digests, and opens a GitOps pull request for
`gitops/environments/dev/images.yaml`. Merge that PR only after the checks succeed.

The application deployment rejects an overlay with empty digests. Qdrant is independently pinned
to the reviewed `qdrant/qdrant:v1.19.1` multi-architecture manifest digest.

## Deploy

Dispatch `application-environment-deployment` on `main`:

- `platform` installs or upgrades Cilium, AWS Load Balancer Controller, External Secrets, Metrics
  Server, KEDA, Kyverno, NVIDIA device plugin, Prometheus/Grafana, Loki, Tempo, OpenTelemetry,
  Alloy, DCGM Exporter, dashboards, and alerts.
- `application` atomically upgrades the application Helm release and rolls back on failure.
- `all` performs both operations in order and is intended for the first environment deployment.

Use the protected `dev`, `staging`, and `prod` GitHub environments for approvals. Production should
require reviewers and prevent self-review. Never make the EKS endpoint public for deployment.

### First-install database ordering

On a missing release, the deployment first installs the chart with frontend, API, ingestion, and
Drive-sync replicas set to zero and KEDA disabled. This creates the service accounts, network
policies, and ExternalSecret required by the migration. Helm can then finish its readiness wait
and run the `post-install` migration hook without waiting for workers that require missing tables.
Only after that install succeeds does a second Helm operation reset the bootstrap overrides and
start the configured replicas and autoscaler. Existing releases keep the `pre-upgrade` migration.
If the second operation fails, the bootstrap revision may remain deployed with zero application
replicas; correct the failure and rerun `application` to retry. Do not run overlapping deployments.

The ALB (and accelerator health-check configuration) uses `/login`, not `/`: the unauthenticated
root returns a 307 redirect, while the target-group health matcher requires HTTP 200.

## Verification

The deployment waits for frontend, API, ingestion-worker, and Drive-sync rollouts, then records deployments, StatefulSets,
pods, ExternalSecrets, and TargetGroupBindings in the private CodeBuild log. Also verify:

1. The ALB target group is healthy and `/login` returns HTTP 200.
2. Cognito authorization redirects back to `/auth/callback` and the PKCE/state checks succeed.
3. API `/live` and `/ready` pass.
4. The migration Job succeeds and Aurora connections use TLS.
5. Qdrant has the expected replica/PVC count for the environment.
6. An S3 upload produces an SQS event and the ingestion worker indexes it.
7. Network policies deny frontend access to Aurora, Qdrant, and Ollama.
8. Prometheus targets are healthy and Grafana dashboards receive metrics, logs, and traces.

## Rollback

Application upgrades use `--atomic`, so a failed rollout automatically returns to the previous Helm
revision. For an explicit rollback, revert the GitOps image PR and dispatch `application` again.
Infrastructure drift is reported but never automatically repaired.
