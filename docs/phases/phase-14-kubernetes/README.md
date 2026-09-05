# Phase 14: Kubernetes

Phase 14 turns the private EKS cluster from Phase 13 into the application runtime. Terraform creates managed node groups and least-privilege EKS Pod Identity associations; pinned Helm releases install controllers; the application chart applies scheduling, availability, storage, scaling, secrets, and network boundaries.

## Node pools and cluster membership

EKS managed node groups join automatically. Terraform gives each group the EKS node IAM role and private subnet IDs. EKS bootstrap configuration on the managed AMI discovers the cluster endpoint and certificate, authenticates through the node role, and registers the kubelet. The control-plane endpoint remains private.

| Pool | Workloads | Isolation |
| --- | --- | --- |
| `general` | frontend, API, Drive sync | `workload=general` label |
| `ingestion` | parsing, OCR, embeddings | `workload=ingestion` and `dedicated=ingestion:NoSchedule` |
| `gpu` | Ollama and future vLLM | `workload=gpu` and `nvidia.com/gpu=true:NoSchedule` |
| `qdrant` | Qdrant StatefulSet only | `workload=qdrant` and `dedicated=qdrant:NoSchedule` |

The chart uses both `nodeSelector` and required node affinity. Dedicated pools require matching tolerations. Stateless deployments use at least two replicas by default, preferred pod anti-affinity, zone topology spreading, and PodDisruptionBudgets. Dev may reduce Qdrant to one replica for cost; staging and production use three replicas across zones.

## Cluster components and identity

`scripts/install_kubernetes_platform.sh` installs the pinned Phase 14 controllers and Phase 15 observability stack. Its additional telemetry bucket, SNS topic, and Grafana-secret prerequisites are documented in the Phase 15 runbook. Terraform installs the EKS Pod Identity Agent and EBS CSI add-on. Cilium chaining retains AWS VPC CNI IP allocation while enforcing standard and Cilium network policies.

Terraform provisions Pod Identity roles for workers to access only project S3/SQS/KMS resources, External Secrets to read the runtime and Aurora secrets, KEDA to read queue depth, AWS Load Balancer Controller to manage only the existing target group, and EBS CSI to manage volumes. The chart binds its frontend Service to the existing WAF-protected ALB with `TargetGroupBinding`; it does not create a second load balancer.

## Qdrant management

Qdrant is a StatefulSet on its dedicated pool. Every replica gets an encrypted `gp3` EBS volume using `WaitForFirstConsumer`. `qdrant-0` starts the cluster and later ordinals join through the headless peer Service. A three-replica production deployment has required host anti-affinity, zone spreading, and a disruption budget. Port 6333 is internal; peer port 6335 is allowed only between Qdrant pods.

Backups use Qdrant collection snapshots copied to project S3. EBS retention is a recovery guard, not the logical backup strategy. Restore and rolling-upgrade drills are required before production sign-off.

## Zero-trust connectivity

A namespace-wide standard `NetworkPolicy` denies all ingress and egress, then permits DNS and these paths:

- public ALB subnet CIDRs to frontend on 3000;
- frontend to API on 8080;
- API to Aurora on 5432, Qdrant on 6333, and Ollama on 11434;
- ingestion and sync workers to S3/SQS over 443, Aurora on 5432, and Qdrant on 6333;
- Qdrant peers to one another on 6335.

Cilium FQDN policies constrain dynamic AWS and Google API HTTPS destinations. Environment values must contain exact ALB subnet CIDRs, the Aurora hostname/private CIDRs, and endpoint CIDRs. Empty defaults fail closed. Never use `0.0.0.0/0` to make a rollout pass.

The source architecture names retrieval and generation as separate logical services, but the current executable implements both inside the API process. Kubernetes therefore enforces API-to-Qdrant and API-to-Ollama at the real pod boundary. Frontend-to-Qdrant, frontend-to-Aurora, and frontend-to-Ollama remain blocked. A future application split can give retrieval and generation separate identities without changing the node-pool design.

## Deployment order

1. Apply Phase 13 and confirm managed node groups are `ACTIVE` and desired nodes are `Ready`.
2. Set `EKS_CLUSTER_NAME`, `AWS_REGION`, and `VPC_ID`, then run `make kubernetes-platform-install` from a network path that reaches the private EKS endpoint.
3. Wait for all controllers and add-ons to become healthy.
4. Copy the environment values example, fill Terraform outputs and the external Qdrant digest,
   then combine it with the reviewed `gitops/environments/dev/images.yaml` project-image overlay
   when deploying into `rag-platform`.
5. Enable the Kyverno image policy after signed images exist and its repository identity is correct.
6. Execute the functional, resilience, policy, and restore checks below.

## Exit criteria

Phase 14 is complete only when all criteria are satisfied.

### Repository validation

- `terraform fmt -check -recursive terraform`, `terraform validate` for dev/staging/prod, and `tflint --recursive` succeed.
- `helm lint` and `helm template` succeed with immutable digests.
- `kubeconform -strict` reports no invalid application or controller resources.
- Terraform and rendered Kubernetes manifests have no unreviewed high or critical Trivy/Checkov findings.
- Controller versions are pinned and no secret value, image tag, or wildcard internet CIDR is committed.

### Cluster and scheduling

- General, ingestion, Qdrant, and GPU node groups are `ACTIVE`; desired nodes join and report `Ready`. GPU may stay at zero in cost-controlled dev.
- Labels, taints, tolerations, selectors, and affinity place every workload only on its intended pool.
- NVIDIA resources are advertised and Ollama schedules when GPU desired capacity is at least one.
- Frontend, API, ingestion, and sync have multiple healthy replicas in staging/production across zones and hosts. A voluntary drain respects PDBs and keeps stateless endpoints available.

### Controllers, identity, and storage

- Cilium, AWS Load Balancer Controller, External Secrets, Metrics Server, KEDA, Kyverno, Pod Identity Agent, EBS CSI, and NVIDIA device plugin are healthy.
- Pod Identity tests prove each role can perform its intended action and cannot perform a representative forbidden action.
- External Secrets creates the runtime Secret without plaintext in Git or Terraform state and refreshes a rotated test value.
- KEDA scales ingestion workers from SQS depth and returns to its minimum after cooldown.
- Qdrant forms one cluster with the expected peers, survives one pod disruption, persists data after recreation, and passes snapshot backup/restore.
- Frontend IP targets are healthy in the Terraform-managed target group; only the ALB is internet-accessible.

### Network and policy enforcement

- Default-deny ingress and egress is active in `rag-platform`.
- Positive probes confirm frontend-to-API, API-to-Aurora/Qdrant/Ollama, workers-to-S3/SQS/Qdrant/Aurora, and Qdrant peer traffic.
- Negative probes confirm frontend cannot connect to Qdrant, Aurora, Ollama, arbitrary internet endpoints, or the Kubernetes API.
- Kyverno rejects an unsigned or tag-only project image and accepts a correctly signed digest.
- Metrics Server serves node/pod metrics; Cilium verdicts show both an allowed and denied probe.

Repository validation is not operational sign-off. Live criteria require a recreated Phase 13 environment. That AWS environment was intentionally destroyed before this phase, so no live criterion is claimed complete.
