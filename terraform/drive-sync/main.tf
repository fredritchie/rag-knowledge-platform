data "aws_caller_identity" "current" {}

#checkov:skip=CKV_AWS_109: AWS KMS key policies require the account-root principal to retain key-administration access.
#checkov:skip=CKV_AWS_111: AWS KMS key policies require the account-root principal to retain key-administration access.
#checkov:skip=CKV_AWS_356: In a KMS key policy, Resource "*" denotes this key and is required by AWS policy syntax.
data "aws_iam_policy_document" "google_oauth_key" {
  statement {
    sid       = "EnableAccountAdministration"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_kms_key" "google_oauth" {
  description             = "Encryption key for the Google Drive OAuth secret"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.google_oauth_key.json
  tags                    = var.tags
}

resource "aws_kms_alias" "google_oauth" {
  name          = "alias/${var.name}-google-oauth"
  target_key_id = aws_kms_key.google_oauth.key_id
}

#checkov:skip=CKV2_AWS_57: Exception expires 2026-12-01. Google OAuth client-secret rotation requires a separately approved Google Cloud rotation workflow; a generic Lambda cannot rotate this refresh-token bundle safely.
resource "aws_secretsmanager_secret" "google_oauth" {
  name                    = var.secret_name
  kms_key_id              = aws_kms_key.google_oauth.arn
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
