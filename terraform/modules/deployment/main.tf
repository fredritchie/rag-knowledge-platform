data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.github_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${var.github_oidc_subject_prefix}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "trigger" {
  name                 = "${var.name}-application-deployer"
  description          = "Starts the VPC-attached application deployment project from GitHub Actions"
  assume_role_policy   = data.aws_iam_policy_document.github_assume.json
  max_session_duration = 3600
  tags                 = var.tags
}

data "aws_iam_policy_document" "trigger" {
  statement {
    actions   = ["codebuild:StartBuild", "codebuild:BatchGetBuilds", "codebuild:StopBuild"]
    resources = [aws_codebuild_project.deploy.arn]
  }
}

resource "aws_iam_role_policy" "trigger" {
  name   = "run-private-deployment"
  role   = aws_iam_role.trigger.id
  policy = data.aws_iam_policy_document.trigger.json
}

data "aws_iam_policy_document" "codebuild_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "codebuild" {
  name               = "${var.name}-private-deployment"
  assume_role_policy = data.aws_iam_policy_document.codebuild_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "logs_key" {
  #checkov:skip=CKV_AWS_109: Account-root administration is required in a KMS key policy.
  #checkov:skip=CKV_AWS_111: Account-root administration is required in a KMS key policy.
  #checkov:skip=CKV_AWS_356: Resource star means this key in KMS key-policy syntax.
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
      identifiers = ["logs.${var.aws_region}.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/codebuild/${var.name}-application-deploy*"]
    }
  }
}

resource "aws_kms_key" "logs" {
  description             = "${var.name} private deployment logs"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.logs_key.json
  tags                    = var.tags
}

resource "aws_cloudwatch_log_group" "deploy" {
  name              = "/aws/codebuild/${var.name}-application-deploy"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.logs.arn
  tags              = var.tags
}

data "aws_iam_policy_document" "codebuild" {
  #checkov:skip=CKV_AWS_109: CodeBuild VPC ENI lifecycle and EC2 Describe APIs require Resource "*"; the role is assumed only by this project.
  #checkov:skip=CKV_AWS_111: AWS documents the required VPC-enabled CodeBuild ENI actions with Resource "*".
  #checkov:skip=CKV_AWS_356: Only EC2 VPC plumbing actions that do not consistently support resource ARNs use Resource "*".
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.deploy.arn}:*"]
  }
  statement {
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:CreateNetworkInterfacePermission",
      "ec2:DeleteNetworkInterface",
      "ec2:DescribeDhcpOptions",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribeRouteTables",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSubnets",
      "ec2:DescribeVpcs",
    ]
    resources = ["*"]
  }
  statement {
    actions   = ["eks:DescribeCluster"]
    resources = [var.eks_cluster_arn]
  }
  statement {
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
      "secretsmanager:PutSecretValue",
    ]
    resources = [var.grafana_admin_secret_arn]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [var.runtime_kms_key_arn]
  }
}

resource "aws_iam_role_policy" "codebuild" {
  name   = "private-kubernetes-deployment"
  role   = aws_iam_role.codebuild.id
  policy = data.aws_iam_policy_document.codebuild.json
}

resource "aws_eks_access_entry" "codebuild" {
  cluster_name  = var.eks_cluster_name
  principal_arn = aws_iam_role.codebuild.arn
  type          = "STANDARD"
  tags          = var.tags
}

resource "aws_eks_access_policy_association" "codebuild" {
  cluster_name  = var.eks_cluster_name
  principal_arn = aws_iam_role.codebuild.arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
  depends_on = [aws_eks_access_entry.codebuild]
}

resource "aws_codebuild_project" "deploy" {
  name           = "${var.name}-application-deploy"
  description    = "VPC-attached Helm deployment for the private EKS cluster"
  service_role   = aws_iam_role.codebuild.arn
  build_timeout  = 120
  queued_timeout = 60

  artifacts { type = "NO_ARTIFACTS" }
  source {
    type      = "NO_SOURCE"
    buildspec = <<-YAML
      version: 0.2
      phases:
        install:
          commands:
            - git clone --filter=blob:none "$REPOSITORY_URL" source
            - cd source && git checkout --detach "$GIT_SHA" && test "$(git rev-parse HEAD)" = "$GIT_SHA"
            - curl -fsSLo /tmp/helm.tar.gz https://get.helm.sh/helm-v3.18.4-linux-amd64.tar.gz
            - echo 'f8180838c23d7c7d797b208861fecb591d9ce1690d8704ed1e4cb8e2add966c1  /tmp/helm.tar.gz' | sha256sum --check
            - tar -xzf /tmp/helm.tar.gz -C /tmp && install /tmp/linux-amd64/helm /usr/local/bin/helm
            - curl -fsSLo /usr/local/bin/kubectl https://dl.k8s.io/release/v1.35.0/bin/linux/amd64/kubectl
            - echo 'a2e984a18a0c063279d692533031c1eff93a262afcc0afdc517375432d060989  /usr/local/bin/kubectl' | sha256sum --check
            - chmod 0755 /usr/local/bin/kubectl
        build:
          commands:
            - cd "$CODEBUILD_SRC_DIR/source"
            - scripts/deploy_kubernetes.sh "$DEPLOY_OPERATION"
      YAML
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    dynamic "environment_variable" {
      for_each = {
        AWS_REGION                = var.aws_region
        AWS_DEFAULT_REGION        = var.aws_region
        DEPLOY_ENVIRONMENT        = var.github_environment
        GITHUB_REPOSITORY         = var.github_repository
        REPOSITORY_URL            = "https://github.com/${var.github_repository}.git"
        EKS_CLUSTER_NAME          = var.eks_cluster_name
        VPC_ID                    = var.vpc_id
        APPLICATION_URL           = var.application_url
        DOCUMENT_BUCKET           = var.document_bucket
        DOCUMENT_KMS_KEY_ARN      = var.document_kms_key_arn
        TELEMETRY_BUCKET          = var.telemetry_bucket
        INGESTION_QUEUE_URL       = var.ingestion_queue_url
        AURORA_ENDPOINT           = var.aurora_endpoint
        AURORA_SECRET_ARN         = var.aurora_secret_arn
        RUNTIME_SECRET_ARN        = var.runtime_secret_arn
        GRAFANA_ADMIN_SECRET_ARN  = var.grafana_admin_secret_arn
        COGNITO_USER_POOL_ID      = var.cognito_user_pool_id
        COGNITO_CLIENT_ID         = var.cognito_client_id
        COGNITO_AUTHORIZE_URL     = var.cognito_authorize_url
        COGNITO_TOKEN_URL         = var.cognito_token_url
        COGNITO_LOGOUT_URL        = var.cognito_logout_url
        SNS_TOPIC_ARN             = var.sns_topic_arn
        ALB_TARGET_GROUP_ARN      = var.alb_target_group_arn
        PUBLIC_SUBNET_CIDRS_JSON  = jsonencode(var.public_subnet_cidrs)
        PRIVATE_SUBNET_CIDRS_JSON = jsonencode(var.private_subnet_cidrs)
        QDRANT_DIGEST             = "sha256:12364fe851b9f17356fc88189fc06d1b521262e04659ec7345975b00c9246a10"
      }
      content {
        name  = environment_variable.key
        value = environment_variable.value
        type  = "PLAINTEXT"
      }
    }
  }

  logs_config {
    cloudwatch_logs {
      group_name  = aws_cloudwatch_log_group.deploy.name
      stream_name = "deployment"
      status      = "ENABLED"
    }
  }

  vpc_config {
    vpc_id             = var.vpc_id
    subnets            = var.private_subnet_ids
    security_group_ids = [var.security_group_id]
  }

  tags = var.tags
}
