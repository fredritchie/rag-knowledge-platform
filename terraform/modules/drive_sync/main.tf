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
}

resource "aws_iam_policy" "sync" {
  name   = var.name
  policy = data.aws_iam_policy_document.sync.json
  tags   = var.tags
}
