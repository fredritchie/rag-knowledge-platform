output "eks_cluster_role_arn" { value = aws_iam_role.eks_cluster.arn }
output "eks_node_role_arn" { value = aws_iam_role.eks_nodes.arn }
output "drift_role_arn" { value = aws_iam_role.drift_detection.arn }
output "ecr_publisher_role_arn" { value = aws_iam_role.ecr_publisher.arn }
output "cognito_user_pool_id" { value = aws_cognito_user_pool.this.id }
output "cognito_client_id" { value = aws_cognito_user_pool_client.web.id }
output "runtime_secret_arn" { value = aws_secretsmanager_secret.runtime.arn }
output "runtime_kms_key_arn" { value = aws_kms_key.runtime.arn }
