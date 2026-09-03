output "application_url" { value = module.platform.application_url }
output "eks_cluster_name" { value = module.platform.eks_cluster_name }
output "document_bucket" { value = module.platform.document_bucket }
output "ingestion_queue_url" { value = module.platform.ingestion_queue_url }
output "ingestion_dlq_url" { value = module.platform.ingestion_dlq_url }
output "ecr_repository_urls" { value = module.platform.ecr_repository_urls }
output "aurora_endpoint" { value = module.platform.aurora_endpoint }
output "aurora_master_secret_arn" {
  value     = module.platform.aurora_master_secret_arn
  sensitive = true
}
output "cognito_user_pool_id" { value = module.platform.cognito_user_pool_id }
output "cognito_client_id" { value = module.platform.cognito_client_id }
output "runtime_secret_arn" { value = module.platform.runtime_secret_arn }
output "drift_role_arn" { value = module.platform.drift_role_arn }
output "sns_topic_arn" { value = module.platform.sns_topic_arn }
output "alb_target_group_arn" { value = module.platform.alb_target_group_arn }
