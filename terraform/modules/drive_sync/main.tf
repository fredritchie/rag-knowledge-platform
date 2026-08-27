data "aws_iam_policy_document" "sync" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${var.bucket_arn}/${var.canonical_prefix}/*"]
  }
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [var.queue_arn]
  }
  statement {
    # The Phase 9 queue is encrypted with a customer-managed key. SQS uses
    # these permissions when the sync worker publishes a Drive delete event.
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.queue_kms_key_arn]
  }
}

resource "aws_iam_policy" "sync" {
  name   = var.name
  policy = data.aws_iam_policy_document.sync.json
  tags   = var.tags
}
