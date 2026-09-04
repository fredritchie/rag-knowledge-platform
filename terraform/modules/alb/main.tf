data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_acm_certificate" "this" {
  count             = var.enable_https ? 1 : 0
  domain_name       = var.domain_name
  validation_method = "DNS"
  tags              = var.tags
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "validation" {
  for_each = var.enable_https ? {
    for option in aws_acm_certificate.this[0].domain_validation_options : option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  } : {}
  allow_overwrite = true
  zone_id         = var.hosted_zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 60
  records         = [each.value.record]
}

resource "aws_acm_certificate_validation" "this" {
  count                   = var.enable_https ? 1 : 0
  certificate_arn         = aws_acm_certificate.this[0].arn
  validation_record_fqdns = [for record in aws_route53_record.validation : record.fqdn]
}

#trivy:ignore:AVD-AWS-0053 The public ALB is the architecture's only internet-facing application resource and is protected by WAF; domainless dev uses HTTP.
resource "aws_lb" "this" {
  #checkov:skip=CKV2_AWS_76: The associated WAF uses AWSManagedRulesKnownBadInputsRuleSet, including Log4Shell inspection.
  #checkov:skip=CKV2_AWS_20: Domainless dev has no certificate and conditionally uses HTTP; production enables the HTTPS listener.
  #checkov:skip=CKV_AWS_150: Deletion protection is mandatory in protected environments and intentionally disabled for disposable dev teardown.
  name                       = var.name
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [var.security_group_id]
  subnets                    = var.public_subnet_ids
  drop_invalid_header_fields = true
  enable_deletion_protection = var.deletion_protection
  access_logs {
    bucket  = aws_s3_bucket.logs.id
    prefix  = "alb/${var.name}"
    enabled = true
  }
  tags = var.tags

  lifecycle {
    precondition {
      condition     = !var.enable_https || (var.domain_name != null && var.hosted_zone_id != null)
      error_message = "domain_name and hosted_zone_id are required when enable_https is true."
    }
  }

  depends_on = [aws_s3_bucket_policy.logs]
}

resource "aws_s3_bucket" "logs" {
  #checkov:skip=CKV_AWS_18: An ALB access-log destination cannot log to itself.
  #checkov:skip=CKV_AWS_144: Short-lived access logs do not require cross-region replication.
  #checkov:skip=CKV_AWS_145: ALB access-log delivery supports Amazon S3 managed encryption, not customer-managed KMS keys.
  #checkov:skip=CKV2_AWS_62: Access logs are consumed from this dedicated bucket without S3 event fan-out.
  bucket_prefix = "${var.name}-logs-"
  force_destroy = var.force_destroy_buckets
  tags          = var.tags
}

resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_ownership_controls" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule { object_ownership = "BucketOwnerEnforced" }
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

#trivy:ignore:AVD-AWS-0132 ALB log delivery supports SSE-S3 but not customer-managed KMS encryption.
resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    id     = "expire"
    status = "Enabled"
    filter {}
    expiration { days = 90 }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}

data "aws_iam_policy_document" "logs" {
  statement {
    sid       = "AllowALBLogDelivery"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.logs.arn}/alb/${var.name}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    principals {
      type        = "Service"
      identifiers = ["logdelivery.elasticloadbalancing.amazonaws.com"]
    }
  }
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.logs.arn, "${aws_s3_bucket.logs.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "logs" {
  bucket = aws_s3_bucket.logs.id
  policy = data.aws_iam_policy_document.logs.json
}

resource "aws_lb_target_group" "application" {
  #checkov:skip=CKV_AWS_378: TLS terminates at the production ALB; traffic to private, security-group-restricted Kubernetes targets uses HTTP.
  name        = "${var.name}-app"
  port        = 3000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    enabled             = true
    path                = "/"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200"
  }
  deregistration_delay = 30
  tags                 = var.tags
}

resource "aws_lb_listener" "https" {
  count             = var.enable_https ? 1 : 0
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.this[0].certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.application.arn
  }
}

#trivy:ignore:AVD-AWS-0054 Domainless dev uses this conditional listener only for infrastructure smoke tests; production enables HTTPS.
resource "aws_lb_listener" "http" {
  #checkov:skip=CKV_AWS_103: Domainless dev deliberately uses HTTP; staging and production require the TLS 1.2+ HTTPS listener above.
  #checkov:skip=CKV_AWS_2: This listener exists only for domainless dev; staging and production create only the HTTPS listener.
  count             = var.enable_https ? 0 : 1
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.application.arn
  }
}

resource "aws_route53_record" "application" {
  count   = var.enable_https ? 1 : 0
  zone_id = var.hosted_zone_id
  name    = var.domain_name
  type    = "A"
  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}

resource "aws_wafv2_web_acl" "this" {
  name  = var.name
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = var.name
    sampled_requests_enabled   = true
  }
  rule {
    name     = "aws-common-rules"
    priority = 10
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-common"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "aws-known-bad-inputs"
    priority = 15
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-known-bad"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "rate-limit"
    priority = 20
    action {
      block {}
    }
    statement {
      rate_based_statement {
        aggregate_key_type = "IP"
        limit              = var.waf_rate_limit
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-rate-limit"
      sampled_requests_enabled   = true
    }
  }
  tags = var.tags
}

data "aws_iam_policy_document" "waf_logs_key" {
  #checkov:skip=CKV_AWS_109: Account-root administration is required in a KMS key policy.
  #checkov:skip=CKV_AWS_111: Account-root administration is required in a KMS key policy.
  #checkov:skip=CKV_AWS_356: Resource star means this KMS key in KMS key-policy syntax.
  statement {
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
  statement {
    actions   = ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${data.aws_region.current.region}.amazonaws.com"]
    }
  }
}

resource "aws_kms_key" "waf_logs" {
  description             = "${var.name} WAF log encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.waf_logs_key.json
  tags                    = var.tags
}

resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-${var.name}"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.waf_logs.arn
  tags              = var.tags
}

resource "aws_wafv2_web_acl_logging_configuration" "this" {
  resource_arn            = aws_wafv2_web_acl.this.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]
  redacted_fields {
    single_header { name = "authorization" }
  }
}

resource "aws_wafv2_web_acl_association" "this" {
  resource_arn = aws_lb.this.arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}
