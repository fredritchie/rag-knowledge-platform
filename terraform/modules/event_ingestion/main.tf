data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  sqs_queue_arns = [
    for queue_name in [var.name, "${var.name}-dlq"] :
    "arn:${data.aws_partition.current.partition}:sqs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:${queue_name}"
  ]
}

#checkov:skip=CKV_AWS_109: AWS KMS key policies require the account-root principal to retain key-administration access.
#checkov:skip=CKV_AWS_111: AWS KMS key policies require the account-root principal to retain key-administration access.
#checkov:skip=CKV_AWS_356: In a KMS key policy, Resource "*" denotes this key and is required by AWS policy syntax.
data "aws_iam_policy_document" "sqs_key" {
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

  statement {
    sid       = "AllowEventBridgeToEncryptQueueMessages"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.s3.arn]
    }
  }

  statement {
    sid       = "AllowSqsToUseKey"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["sqs.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "kms:CallerAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:sqs:arn"
      values   = local.sqs_queue_arns
    }
  }
}

resource "aws_kms_key" "sqs" {
  description             = "Phase 9 EventBridge and SQS ingestion encryption"
  deletion_window_in_days = var.kms_deletion_window_in_days
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.sqs_key.json
  tags                    = var.tags
}

resource "aws_kms_alias" "sqs" {
  name          = "alias/${var.name}-sqs"
  target_key_id = aws_kms_key.sqs.key_id
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-dlq"
  message_retention_seconds = var.dlq_retention_seconds
  kms_master_key_id         = aws_kms_key.sqs.arn
  tags                      = var.tags
}

resource "aws_sqs_queue" "ingestion" {
  name                       = var.name
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = 20
  kms_master_key_id          = aws_kms_key.sqs.arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
  tags = var.tags
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.ingestion.arn]
  })
}

resource "aws_cloudwatch_event_rule" "s3" {
  name = "${var.name}-s3-events"
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created", "Object Deleted"]
    detail = {
      bucket = { name = [var.bucket_name] }
      object = { key = [{ prefix = var.object_prefix }] }
    }
  })
  tags = var.tags
}

resource "aws_cloudwatch_event_target" "sqs" {
  rule = aws_cloudwatch_event_rule.s3.name
  arn  = aws_sqs_queue.ingestion.arn
}

data "aws_iam_policy_document" "eventbridge_to_sqs" {
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingestion.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.s3.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "ingestion" {
  queue_url = aws_sqs_queue.ingestion.id
  policy    = data.aws_iam_policy_document.eventbridge_to_sqs.json
}

resource "aws_s3_bucket_notification" "eventbridge" {
  bucket      = var.bucket_name
  eventbridge = true
}

resource "aws_s3_bucket_versioning" "canonical" {
  count  = var.enable_bucket_versioning ? 1 : 0
  bucket = var.bucket_name
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.name}-dlq-not-empty"
  alarm_description   = "At least one ingestion event exhausted its retries and entered the DLQ."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.dlq_alarm_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  tags                = var.tags
}

data "aws_iam_policy_document" "worker" {
  statement {
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes", "sqs:SendMessage"]
    resources = [aws_sqs_queue.ingestion.arn, aws_sqs_queue.dlq.arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = ["${var.bucket_arn}/*"]
  }
  statement {
    # SQS calls KMS on behalf of the worker when it receives encrypted event
    # messages. Restrict decrypt/data-key access to this module's queue key.
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.sqs.arn]
  }
}

resource "aws_iam_policy" "worker" {
  name   = "${var.name}-worker"
  policy = data.aws_iam_policy_document.worker.json
  tags   = var.tags
}
