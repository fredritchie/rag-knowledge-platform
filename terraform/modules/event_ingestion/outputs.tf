output "queue_url" { value = aws_sqs_queue.ingestion.id }
output "queue_arn" { value = aws_sqs_queue.ingestion.arn }
output "dlq_url" { value = aws_sqs_queue.dlq.id }
output "dlq_arn" { value = aws_sqs_queue.dlq.arn }
output "worker_policy_arn" { value = aws_iam_policy.worker.arn }
output "dlq_alarm_arn" { value = aws_cloudwatch_metric_alarm.dlq_not_empty.arn }
output "sqs_kms_key_arn" { value = aws_kms_key.sqs.arn }
