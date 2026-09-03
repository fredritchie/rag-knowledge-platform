output "application_url" { value = module.edge.application_url }
output "eks_cluster_name" { value = module.kubernetes.cluster_name }
output "document_bucket" { value = module.documents.bucket_id }
output "ingestion_queue_url" { value = module.queues.queue_url }
output "ingestion_dlq_url" { value = module.queues.dlq_url }
output "ecr_repository_urls" { value = module.ecr.repository_urls }
output "aurora_endpoint" { value = module.database.cluster_endpoint }
output "aurora_master_secret_arn" {
  value     = module.database.master_user_secret_arn
  sensitive = true
}
output "cognito_user_pool_id" { value = module.iam.cognito_user_pool_id }
output "cognito_client_id" { value = module.iam.cognito_client_id }
output "runtime_secret_arn" { value = module.iam.runtime_secret_arn }
output "drift_role_arn" { value = module.iam.drift_role_arn }
output "ecr_publisher_role_arn" { value = module.iam.ecr_publisher_role_arn }
output "sns_topic_arn" { value = module.monitoring.sns_topic_arn }
output "alb_target_group_arn" { value = module.edge.target_group_arn }
