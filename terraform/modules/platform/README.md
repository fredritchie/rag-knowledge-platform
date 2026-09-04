# Platform composition module

Connects the focused Phase 13 modules into one environment stack. Environment roots remain intentionally thin so all three environments have identical topology and differ only by reviewed input values and remote-state keys.

The module also provisions the KMS-encrypted telemetry bucket used by Loki and Tempo, EKS Pod Identity access scoped to that bucket, and read-only CloudWatch access for Grafana's SQS dashboards. None of these identities grants application data access.
