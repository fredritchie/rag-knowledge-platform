resource "aws_secretsmanager_secret" "google_oauth" {
  name                    = var.secret_name
  recovery_window_in_days = var.recovery_window_in_days
  tags                    = var.tags
}

module "drive_sync" {
  source = "../modules/drive_sync"

  name              = var.name
  bucket_arn        = var.bucket_arn
  queue_arn         = var.queue_arn
  queue_kms_key_arn = var.queue_kms_key_arn
  secret_arns       = [aws_secretsmanager_secret.google_oauth.arn]
  canonical_prefix  = var.canonical_prefix
  tags              = var.tags
}

resource "aws_iam_role_policy_attachment" "sync_worker" {
  role       = var.worker_role_name
  policy_arn = module.drive_sync.policy_arn
}
