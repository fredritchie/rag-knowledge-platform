output "queue_url" {
  value = module.event_ingestion.queue_url
}

output "dlq_url" {
  value = module.event_ingestion.dlq_url
}

output "worker_policy_arn" {
  value = module.event_ingestion.worker_policy_arn
}

output "dlq_alarm_arn" {
  value = module.event_ingestion.dlq_alarm_arn
}

output "sqs_kms_key_arn" {
  value = module.event_ingestion.sqs_kms_key_arn
}
