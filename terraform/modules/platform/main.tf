data "aws_caller_identity" "current" {}

data "aws_ec2_managed_prefix_list" "cloudfront_origin" {
  count = var.enable_https ? 0 : 1
  name  = "com.amazonaws.global.cloudfront.origin-facing"
}

locals {
  name = "rag-platform-${var.environment}"
  tags = merge(var.tags, {
    Project = "rag-platform", Environment = var.environment, ManagedBy = "Terraform"
  })
  bucket_name           = "rag-platform-${var.environment}-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  telemetry_bucket_name = "rag-platform-${var.environment}-telemetry-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  github_oidc_subject_prefix = coalesce(
    var.github_oidc_subject_prefix,
    "repo:${var.github_repository}",
  )
}

module "vpc" {
  source                     = "../vpc"
  name                       = local.name
  vpc_cidr                   = var.vpc_cidr
  availability_zones         = var.availability_zones
  public_subnet_cidrs        = var.public_subnet_cidrs
  private_subnet_cidrs       = var.private_subnet_cidrs
  single_nat_gateway         = var.single_nat_gateway
  alb_ingress_port           = var.enable_https ? 443 : 80
  alb_ingress_prefix_list_id = var.enable_https ? null : data.aws_ec2_managed_prefix_list.cloudfront_origin[0].id
  tags                       = local.tags
}

module "documents" {
  source        = "../s3"
  name          = local.bucket_name
  force_destroy = !var.deletion_protection
  tags          = local.tags
}

module "telemetry" {
  source        = "../s3"
  name          = local.telemetry_bucket_name
  force_destroy = !var.deletion_protection
  tags          = merge(local.tags, { DataClass = "operational-telemetry" })
}

module "queues" {
  source            = "../sqs"
  name              = "${local.name}-ingestion"
  source_bucket_arn = module.documents.bucket_arn
  alarm_actions     = [module.monitoring.sns_topic_arn]
  tags              = local.tags
}

resource "aws_s3_bucket_notification" "documents" {
  bucket = module.documents.bucket_id
  queue {
    queue_arn     = module.queues.queue_arn
    events        = ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"]
    filter_prefix = "tenants/"
  }
  depends_on = [module.queues]
}

module "ecr" {
  source       = "../ecr"
  name_prefix  = "rag"
  repositories = ["frontend", "api", "ingestion-worker", "drive-sync", "ollama-runtime"]
  kms_key_arn  = module.documents.kms_key_arn
  force_delete = !var.deletion_protection
  tags         = local.tags
}

module "iam" {
  source                     = "../iam"
  name                       = local.name
  github_oidc_subject_prefix = local.github_oidc_subject_prefix
  github_environment         = var.environment
  github_oidc_provider_arn   = var.github_oidc_provider_arn
  state_bucket_arn           = var.state_bucket_arn
  state_kms_key_arn          = var.state_kms_key_arn
  sns_topic_arn              = module.monitoring.sns_topic_arn
  alert_kms_key_arn          = module.monitoring.kms_key_arn
  ecr_repository_arns        = values(module.ecr.repository_arns)
  callback_urls              = ["${module.edge.application_url}/auth/callback"]
  logout_urls                = ["${module.edge.application_url}/login"]
  deletion_protection        = var.deletion_protection
  tags                       = local.tags
}

moved {
  from = module.deployment.aws_security_group.codebuild
  to   = aws_security_group.deployment
}

resource "aws_security_group" "deployment" {
  #checkov:skip=CKV2_AWS_5: Attached to both the EKS control plane and CodeBuild VPC interfaces.
  name_prefix = "${local.name}-deployment-"
  description = "Shared security group for private Kubernetes deployments"
  vpc_id      = module.vpc.vpc_id
  ingress {
    description = "Kubernetes API between members of the deployment security group"
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    self        = true
  }
  egress {
    description = "Private VPC resources and EKS endpoint"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = [var.vpc_cidr]
  }
  #trivy:ignore:AVD-AWS-0104 The private build needs HTTPS through NAT for GitHub and pinned Helm repositories.
  egress {
    description = "HTTPS through NAT for source and chart downloads"
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = merge(local.tags, { Name = "${local.name}-deployment" })
  lifecycle { create_before_destroy = true }
}

module "kubernetes" {
  source                        = "../kubernetes"
  name                          = local.name
  kubernetes_version            = var.kubernetes_version
  private_subnet_ids            = module.vpc.private_subnet_ids
  security_group_id             = module.vpc.kubernetes_security_group_id
  additional_security_group_ids = [aws_security_group.deployment.id]
  cluster_role_arn              = module.iam.eks_cluster_role_arn
  node_role_arn                 = module.iam.eks_node_role_arn
  general_instance_types        = var.general_instance_types
  qdrant_instance_types         = var.qdrant_instance_types
  ingestion_instance_types      = var.ingestion_instance_types
  gpu_instance_types            = var.gpu_instance_types
  general_desired_size          = var.general_desired_size
  qdrant_desired_size           = var.qdrant_desired_size
  ingestion_desired_size        = var.ingestion_desired_size
  gpu_desired_size              = var.gpu_desired_size
  tags                          = local.tags
}

moved {
  from = module.vpc.aws_security_group.database
  to   = aws_security_group.database
}

resource "aws_security_group" "database" {
  #checkov:skip=CKV2_AWS_5: Attached to Aurora in the RDS module.
  name_prefix = "${local.name}-database-"
  description = "PostgreSQL from Kubernetes only"
  vpc_id      = module.vpc.vpc_id
  ingress {
    description     = "PostgreSQL from platform workloads"
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [module.vpc.kubernetes_security_group_id]
  }
  ingress {
    description     = "PostgreSQL from EKS managed nodes"
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [module.kubernetes.cluster_primary_security_group_id]
  }
  egress {
    description = "Return traffic"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = [var.vpc_cidr]
  }
  tags = merge(local.tags, { Name = "${local.name}-database" })
  lifecycle { create_before_destroy = true }
}

module "database" {
  source              = "../rds"
  name                = local.name
  private_subnet_ids  = module.vpc.private_subnet_ids
  security_group_id   = aws_security_group.database.id
  instance_class      = var.aurora_instance_class
  instance_count      = var.aurora_instance_count
  deletion_protection = var.deletion_protection
  skip_final_snapshot = !var.deletion_protection
  tags                = local.tags
}

module "edge" {
  source                = "../alb"
  name                  = "${local.name}-alb"
  enable_https          = var.enable_https
  domain_name           = var.domain_name
  hosted_zone_id        = var.hosted_zone_id
  certificate_arn       = var.certificate_arn
  vpc_id                = module.vpc.vpc_id
  public_subnet_ids     = module.vpc.public_subnet_ids
  security_group_id     = module.vpc.alb_security_group_id
  deletion_protection   = var.deletion_protection
  force_destroy_buckets = !var.deletion_protection
  tags                  = local.tags
}

module "monitoring" {
  source                 = "../monitoring"
  name                   = local.name
  alert_email_addresses  = var.alert_email_addresses
  alb_arn_suffix         = module.edge.alb_arn_suffix
  rds_cluster_identifier = module.database.cluster_identifier
  eks_cluster_name       = module.kubernetes.cluster_name
  tags                   = local.tags
}

module "deployment" {
  source = "../deployment"

  name                       = local.name
  aws_region                 = var.aws_region
  github_repository          = var.github_repository
  github_oidc_subject_prefix = local.github_oidc_subject_prefix
  github_oidc_provider_arn   = var.github_oidc_provider_arn
  github_environment         = var.environment
  vpc_id                     = module.vpc.vpc_id
  private_subnet_ids         = module.vpc.private_subnet_ids
  security_group_id          = aws_security_group.deployment.id
  eks_cluster_name           = module.kubernetes.cluster_name
  eks_cluster_arn            = module.kubernetes.cluster_arn
  application_url            = module.edge.application_url
  document_bucket            = module.documents.bucket_id
  document_kms_key_arn       = module.documents.kms_key_arn
  telemetry_bucket           = module.telemetry.bucket_id
  ingestion_queue_url        = module.queues.queue_url
  aurora_endpoint            = module.database.cluster_endpoint
  aurora_secret_arn          = module.database.master_user_secret_arn
  runtime_secret_arn         = module.iam.runtime_secret_arn
  grafana_admin_secret_arn   = module.iam.grafana_admin_secret_arn
  runtime_kms_key_arn        = module.iam.runtime_kms_key_arn
  cognito_user_pool_id       = module.iam.cognito_user_pool_id
  cognito_client_id          = module.iam.cognito_client_id
  cognito_authorize_url      = module.iam.cognito_authorize_url
  cognito_token_url          = module.iam.cognito_token_url
  cognito_logout_url         = module.iam.cognito_logout_url
  sns_topic_arn              = module.monitoring.sns_topic_arn
  alb_target_group_arn       = module.edge.target_group_arn
  public_subnet_cidrs        = var.public_subnet_cidrs
  private_subnet_cidrs       = var.private_subnet_cidrs
  tags                       = local.tags
}
