output "sns_topic_arn" { value = aws_sns_topic.alerts.arn }
output "kms_key_arn" { value = aws_kms_key.this.arn }
output "dashboard_name" { value = aws_cloudwatch_dashboard.this.dashboard_name }
output "application_log_group" { value = aws_cloudwatch_log_group.application.name }
