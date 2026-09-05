output "eks_cluster_role_arn" { value = aws_iam_role.eks_cluster.arn }
output "eks_node_role_arn" { value = aws_iam_role.eks_nodes.arn }
output "drift_role_arn" { value = aws_iam_role.drift_detection.arn }
output "ecr_publisher_role_arn" { value = aws_iam_role.ecr_publisher.arn }
output "cognito_user_pool_id" { value = aws_cognito_user_pool.this.id }
output "cognito_client_id" { value = aws_cognito_user_pool_client.web.id }
output "cognito_domain" { value = aws_cognito_user_pool_domain.this.domain }
output "cognito_authorize_url" {
  value = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${data.aws_region.current.region}.amazoncognito.com/oauth2/authorize"
}
output "cognito_token_url" {
  value = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${data.aws_region.current.region}.amazoncognito.com/oauth2/token"
}
output "cognito_logout_url" {
  value = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${data.aws_region.current.region}.amazoncognito.com/logout"
}
output "runtime_secret_arn" { value = aws_secretsmanager_secret.runtime.arn }
output "grafana_admin_secret_arn" { value = aws_secretsmanager_secret.grafana_admin.arn }
output "runtime_kms_key_arn" { value = aws_kms_key.runtime.arn }
