output "google_oauth_secret_arn" {
  value = aws_secretsmanager_secret.google_oauth.arn
}

output "google_oauth_secret_name" {
  value = aws_secretsmanager_secret.google_oauth.name
}

output "sync_worker_policy_arn" {
  value = module.drive_sync.policy_arn
}
