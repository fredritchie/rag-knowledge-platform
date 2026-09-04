# Observability third-party manifest review

Review date: 2026-09-04

The pinned kube-prometheus-stack manifest has nine Trivy high/critical findings after all configurable workloads were hardened. `scripts/verify_observability_findings.sh` fails CI if that exact finding-ID/count set changes. This is not a blanket Trivy ignore: application manifests, Terraform, and every other Phase 15 component must remain clean.

## Accepted capabilities

| Finding | Resource | Why it is required | Compensating controls |
| --- | --- | --- | --- |
| KSV-0009, KSV-0010, KSV-0121 | Prometheus node-exporter DaemonSet | Host networking, host PID visibility, and read-only host `/proc`, `/sys`, and root mounts are how node-exporter observes host metrics. | Official pinned chart; dedicated monitoring namespace; no cloud IAM identity; read-only mounts; private metrics Service. |
| KSV-0041 | Prometheus Operator ClusterRole | The operator reads referenced Secrets to reconcile TLS and authentication settings for managed monitoring resources. | Read access only; Kubernetes audit logging; no application cloud role; chart version pinning and upgrade review. |
| KSV-0045 (two rules), KSV-0056 (two rules) | Prometheus Operator ClusterRole | The controller must reconcile its CRDs and their generated Services/Endpoints. Trivy treats controller wildcard verbs on the dedicated API group and service reconciliation as critical/high. | Scope is the official operator controller; admission and Kyverno policy remain active; runtime identity has no AWS privileges. |
| KSV-0114 | Prometheus Operator admission hook role | Helm's certificate patch hook updates the operator's own validating/mutating webhook configurations during installation and upgrade. | Hook-scoped service account; no AWS identity; audited chart upgrades; webhook configuration is inspected after install. |

All other initial findings were removed by namespaced RBAC, dropping secret discovery, non-root users, read-only root filesystems, seccomp, dropped capabilities, and disabling DCGM profiling privileges. Any count or ID change requires a fresh review before merge.
