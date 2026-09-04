# Helm

`platform/` pins Cilium, AWS Load Balancer Controller, External Secrets Operator, Metrics Server,
KEDA, Kyverno, the NVIDIA device plugin, kube-prometheus-stack, Loki, Tempo, OpenTelemetry
Collector, Alloy, and DCGM Exporter. `observability/` provisions the four Grafana dashboards and
Prometheus alert rules. Install them first with
`scripts/install_kubernetes_platform.sh` after setting `EKS_CLUSTER_NAME`, `AWS_REGION`, and
`VPC_ID`, plus the Terraform `TELEMETRY_BUCKET` and `SNS_TOPIC_ARN` outputs. Create the
`monitoring/grafana-admin` Secret with `admin-user` and `admin-password` keys before running the
installer; never place those values in a Helm values file.

`rag-platform/` deploys the frontend, API, ingestion worker, Drive sync worker, migration Job,
Ollama runtime, and persistent Qdrant cluster. Every image requires an immutable `sha256:` digest;
tag-only deployments fail rendering.

Copy `values-dev.yaml.example` and replace every ARN, endpoint, and CIDR. Empty network defaults
deliberately fail closed. Install into the `rag-platform` namespace so Terraform Pod Identity
associations match. Enable `admissionPolicy.enabled` only after Kyverno is healthy, signed images
exist, and the repository identity has been replaced.
