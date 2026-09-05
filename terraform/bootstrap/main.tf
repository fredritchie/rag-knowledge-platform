data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "state_key" {
  #checkov:skip=CKV_AWS_109: Account-root administration is required in a KMS key policy.
  #checkov:skip=CKV_AWS_111: Account-root administration is required in a KMS key policy.
  #checkov:skip=CKV_AWS_356: Resource star means this KMS key in KMS key-policy syntax.
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

resource "aws_kms_key" "state" {
  description             = "Terraform remote-state encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.state_key.json
}

resource "aws_kms_alias" "state" {
  name          = "alias/rag-platform-terraform-state"
  target_key_id = aws_kms_key.state.key_id
}

resource "aws_s3_bucket" "state" {
  #checkov:skip=CKV_AWS_18: A state bucket cannot server-log to itself; CloudTrail data events are configured at account level.
  #checkov:skip=CKV_AWS_144: State versions provide recovery; cross-region replication requires a separately approved recovery account/region.
  #checkov:skip=CKV2_AWS_62: State changes are monitored by the scheduled drift workflow instead of object notifications.
  bucket = var.state_bucket_name
  lifecycle { prevent_destroy = true }
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "retain-state-history"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 365 }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
  depends_on = [aws_s3_bucket_versioning.state]
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    bucket_key_enabled = true
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.state.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "state_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
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

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_bucket.json
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_github_oidc_provider ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
  tags            = var.tags
}

locals {
  github_oidc_provider_arn = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : var.existing_github_oidc_provider_arn
}

data "aws_iam_policy_document" "terraform_deploy_assume" {
  statement {
    sid     = "GitHubEnvironmentOidc"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${var.github_oidc_subject_prefix}:environment:${var.terraform_deploy_environment}"]
    }
  }
}

resource "aws_iam_role" "terraform_deploy" {
  name                 = "rag-platform-terraform-${var.terraform_deploy_environment}"
  description          = "GitHub Actions Terraform deployment role for ${var.terraform_deploy_environment}"
  assume_role_policy   = data.aws_iam_policy_document.terraform_deploy_assume.json
  max_session_duration = 3600
  tags                 = merge(var.tags, { Component = "terraform-deployment", Environment = var.terraform_deploy_environment })
}

resource "aws_iam_role_policy_attachment" "terraform_deploy_power_user" {
  role       = aws_iam_role.terraform_deploy.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

data "aws_iam_policy_document" "terraform_deploy_iam" {
  statement {
    sid = "ManageProjectRoles"
    actions = [
      "iam:AttachRolePolicy",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:DetachRolePolicy",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
      "iam:ListRoleTags",
      "iam:PassRole",
      "iam:PutRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.terraform_managed_name_prefix}-*"]
  }

  statement {
    sid = "ManageProjectPolicies"
    actions = [
      "iam:CreatePolicy",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicy",
      "iam:DeletePolicyVersion",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicyTags",
      "iam:ListPolicyVersions",
      "iam:TagPolicy",
      "iam:UntagPolicy",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.terraform_managed_name_prefix}-*"]
  }

  statement {
    sid       = "CreateRequiredServiceLinkedRoles"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/*"]
    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values = [
        "autoscaling.amazonaws.com",
        "eks.amazonaws.com",
        "eks-nodegroup.amazonaws.com",
        "elasticloadbalancing.amazonaws.com",
        "rds.amazonaws.com",
        "spot.amazonaws.com",
      ]
    }
  }

  statement {
    sid       = "ReadRequiredServiceLinkedRoles"
    actions   = ["iam:GetRole"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/*"]
  }
}

resource "aws_iam_role_policy" "terraform_deploy_iam" {
  name   = "manage-rag-platform-iam"
  role   = aws_iam_role.terraform_deploy.id
  policy = data.aws_iam_policy_document.terraform_deploy_iam.json
}

data "aws_iam_policy_document" "additional_terraform_deploy_assume" {
  for_each = var.additional_terraform_deploy_environments
  statement {
    sid     = "GitHubEnvironmentOidc"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${var.github_oidc_subject_prefix}:environment:${each.key}"]
    }
  }
}

resource "aws_iam_role" "additional_terraform_deploy" {
  for_each             = var.additional_terraform_deploy_environments
  name                 = "rag-platform-terraform-${each.key}"
  description          = "GitHub Actions Terraform deployment role for ${each.key}"
  assume_role_policy   = data.aws_iam_policy_document.additional_terraform_deploy_assume[each.key].json
  max_session_duration = 3600
  tags                 = merge(var.tags, { Component = "terraform-deployment", Environment = each.key })
}

resource "aws_iam_role_policy_attachment" "additional_terraform_deploy_power_user" {
  for_each   = var.additional_terraform_deploy_environments
  role       = aws_iam_role.additional_terraform_deploy[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

data "aws_iam_policy_document" "additional_terraform_deploy_iam" {
  for_each = var.additional_terraform_deploy_environments
  statement {
    sid = "ManageProjectRoles"
    actions = [
      "iam:AttachRolePolicy",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:DetachRolePolicy",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
      "iam:ListRoleTags",
      "iam:PassRole",
      "iam:PutRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/rag-platform-${each.key}-*"]
  }
  statement {
    sid = "ManageProjectPolicies"
    actions = [
      "iam:CreatePolicy",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicy",
      "iam:DeletePolicyVersion",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicyTags",
      "iam:ListPolicyVersions",
      "iam:TagPolicy",
      "iam:UntagPolicy",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/rag-platform-${each.key}-*"]
  }
  statement {
    sid       = "CreateRequiredServiceLinkedRoles"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/*"]
    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values = [
        "autoscaling.amazonaws.com",
        "eks.amazonaws.com",
        "eks-nodegroup.amazonaws.com",
        "elasticloadbalancing.amazonaws.com",
        "rds.amazonaws.com",
        "spot.amazonaws.com",
      ]
    }
  }

  statement {
    sid       = "ReadRequiredServiceLinkedRoles"
    actions   = ["iam:GetRole"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/*"]
  }
}

resource "aws_iam_role_policy" "additional_terraform_deploy_iam" {
  for_each = var.additional_terraform_deploy_environments
  name     = "manage-rag-platform-iam"
  role     = aws_iam_role.additional_terraform_deploy[each.key].id
  policy   = data.aws_iam_policy_document.additional_terraform_deploy_iam[each.key].json
}
