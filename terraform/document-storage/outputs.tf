output "bucket_name" {
  value       = aws_s3_bucket.documents.bucket
  description = "Set as RAG__STORAGE__BUCKET."
}

output "bucket_arn" {
  value       = aws_s3_bucket.documents.arn
  description = "Canonical document bucket ARN."
}

output "storage_region" {
  value       = var.aws_region
  description = "Set as RAG__STORAGE__REGION."
}

output "server_side_encryption" {
  value       = "AES256"
  description = "Set as RAG__STORAGE__SERVER_SIDE_ENCRYPTION."
}

output "application_role_arn" {
  value       = aws_iam_role.document_app.arn
  description = "IAM role granted access to tenant-prefixed document objects."
}

output "instance_profile_name" {
  value       = aws_iam_instance_profile.document_app.name
  description = "Attach to the EC2 application instance if ec2_instance_id was not supplied."
}
