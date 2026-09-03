output "cluster_identifier" { value = aws_rds_cluster.this.cluster_identifier }
output "cluster_endpoint" { value = aws_rds_cluster.this.endpoint }
output "reader_endpoint" { value = aws_rds_cluster.this.reader_endpoint }
output "port" { value = aws_rds_cluster.this.port }
output "master_user_secret_arn" {
  value     = aws_rds_cluster.this.master_user_secret[0].secret_arn
  sensitive = true
}
output "kms_key_arn" { value = aws_kms_key.this.arn }
