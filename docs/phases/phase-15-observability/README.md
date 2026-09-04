# Phase 15: Observability

Phase 15 makes the application and Kubernetes platform diagnosable without recording user prompts, retrieved passages, document text, credentials, or tokens. Prometheus supplies metrics and alert evaluation, Grafana supplies dashboards, Loki stores logs, Tempo stores traces, and Alertmanager publishes actionable alerts to the existing encrypted SNS topic.

## Architecture

Application processes expose Prometheus metrics on port 9090 and export sampled OTLP/HTTP traces to a two-replica OpenTelemetry Collector. The collector batches and forwards traces to Tempo. Grafana Alloy runs on every node, reads Kubernetes container logs, parses the application JSON envelope, and forwards logs to Loki. Loki and Tempo use the Terraform-managed, KMS-encrypted telemetry S3 bucket through EKS Pod Identity.

`kube-prometheus-stack` installs Prometheus, Grafana, Alertmanager, node-exporter, and kube-state-metrics. DCGM Exporter runs only on GPU nodes. All chart versions are pinned in `helm/platform/versions.env`. The `rag-observability` chart supplies Platform, RAG, Ingestion, and GPU dashboards plus application alert rules.

## Application signals

Every application log is JSON with these stable fields:

```json
{"timestamp":"...","level":"INFO","service":"api","request_id":"...","tenant_id":"...","trace_id":"...","message":"..."}
```

Optional fields are limited to bounded operational metadata such as component, operation, status, latency, document ID, and job ID. The formatter intentionally ignores arbitrary log-record extras. Code must never log authorization headers, secret values, prompts, retrieved text, generated answers, or document content.

The root `rag.request` trace contains the implemented stages `auth.validate`, `authorization.resolve`, `query.embed`, `bm25.search`, `qdrant.search`, `rerank`, `prompt.build`, and `llm.generate`. Trace sampling is parent-based and configurable with `RAG__OBSERVABILITY__TRACE_SAMPLE_RATIO`.

## Dashboards

- Platform: node and pod health, CPU, memory, disk, network, restarts, and structured logs.
- RAG: query rate, retrieval/reranker/generation/end-to-end latency, errors, unsupported questions, citation count, generated tokens, and recent traces.
- Ingestion: SQS depth and oldest-message age, DLQ depth, documents/minute, failed ingestion, and Drive lag. Set the dashboard queue variables to the Terraform queue names.
- GPU: utilization, VRAM, temperature, power, and generation tokens/second.

Grafana obtains SQS metrics from CloudWatch using a read-only Pod Identity role. Alertmanager has a separate role that can publish only to the project SNS topic. Grafana, Loki, Tempo, and application workers do not share an IAM role.

## Deployment

Apply the Terraform environment first. From a machine that can reach the private EKS endpoint:

```bash
export EKS_CLUSTER_NAME="$(terraform -chdir=terraform/environments/dev output -raw eks_cluster_name)"
export AWS_REGION=us-east-1
export VPC_ID="$(aws eks describe-cluster --name "$EKS_CLUSTER_NAME" --query 'cluster.resourcesVpcConfig.vpcId' --output text)"
export TELEMETRY_BUCKET="$(terraform -chdir=terraform/environments/dev output -raw telemetry_bucket)"
export SNS_TOPIC_ARN="$(terraform -chdir=terraform/environments/dev output -raw sns_topic_arn)"
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl -n monitoring create secret generic grafana-admin \
  --from-literal=admin-user=admin \
  --from-literal=admin-password='replace-with-a-generated-secret'
make kubernetes-platform-install
```

Deploy the application chart afterward. Its default observability endpoint already targets the collector in `monitoring`. Do not expose Prometheus, Grafana, Loki, Tempo, or application metrics through the public ALB; use authenticated port forwarding or an approved private access path.

## Exit criteria

Phase 15 is complete only when every repository and live-runtime criterion below passes.

### Repository validation

- Python formatting, Ruff, unit tests, Bandit, and dependency audit pass.
- Terraform formatting/validation, TFLint, Checkov, and Trivy configuration scanning pass with no unreviewed high or critical finding. The narrowly accepted upstream controller/exporter capabilities are recorded in `docs/security/observability-third-party-review.md` and CI rejects any change to their finding set.
- Every observability chart is version-pinned; Helm lint/template and strict kubeconform validation pass.
- All four dashboard JSON files parse and contain every requested panel; PrometheusRule expressions render successfully.
- Tests prove the structured formatter emits the required fields and drops arbitrary sensitive extras.
- No secret, prompt, retrieved passage, answer, document content, public observability endpoint, or wildcard application ingress is committed.

### Metrics and dashboards

- Prometheus, both Alertmanager replicas, Grafana, node-exporter, kube-state-metrics, and DCGM Exporter targets are healthy; the DCGM target may be absent only when dev GPU capacity is intentionally zero.
- API, ingestion-worker, and Drive-sync ServiceMonitors are `UP`, and the monitoring namespace can scrape port 9090 while unapproved namespaces cannot.
- Platform, RAG, Ingestion, and GPU dashboards load without datasource or query errors and display current test traffic.
- A test RAG request updates query rate, all applicable stage histograms, citations, end-to-end latency, errors/outcome, and generation throughput.
- An ingestion/Drive test updates document outcome and Drive-lag metrics; CloudWatch panels show the correct queue, oldest-message age, and DLQ.

### Logs and traces

- Alloy is healthy on every schedulable node and recent JSON logs are queryable in Loki by namespace, service, level, request ID, tenant ID, and trace ID.
- A controlled log inspection confirms no prompts, retrieved text, generated answers, credentials, authorization headers, or document content are present.
- A sampled RAG request appears in Tempo as one `rag.request` trace with the implemented child stages and correlated request/tenant attributes.
- Trace failures include error status without leaking request or document content; Grafana links traces to the matching Loki time range.

### Alerting, durability, and isolation

- A controlled synthetic alert reaches Alertmanager, publishes through the encrypted SNS topic, and sends a resolved notification.
- High error rate, high p95 RAG latency, ingestion failure, stale Drive sync, and high GPU temperature rules evaluate without errors.
- Grafana can read CloudWatch metrics but cannot publish SNS or access project objects; Alertmanager can publish only to the alert topic; Loki and Tempo can access only the telemetry bucket.
- Restart tests preserve Grafana state, Prometheus data, Loki logs, and Tempo traces. S3 objects are KMS encrypted and lifecycle/versioning controls are active.
- Prometheus, Grafana, Loki, Tempo, collectors, and metrics endpoints remain private and are not reachable through the internet-facing ALB.

Repository validation is not operational sign-off. Live criteria require a deployed Phase 13/14 environment and generated traffic. The AWS environment is currently intentionally destroyed, so this implementation does not claim the live-runtime criteria are complete.
