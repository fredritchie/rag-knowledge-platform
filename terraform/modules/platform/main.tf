data "aws_caller_identity" "current" {}

locals {
  name = "rag-platform-${var.environment}"
  tags = merge(var.tags, {
    Project = "rag-platform", Environment = var.environment, ManagedBy = "Terraform"
  })
  bucket_name = "rag-platform-${var.environment}-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  auth_domain = coalesce(var.domain_name, "localhost:3000")
  github_oidc_subject_prefix = coalesce(
    var.github_oidc_subject_prefix,
    "repo:${var.github_repository}",
  )
}

module "vpc" {
  source               = "../vpc"
  name                 = local.name
  vpc_cidr             = var.vpc_cidr
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway   = var.single_nat_gateway
  alb_ingress_port     = var.enable_https ? 443 : 80
  tags                 = local.tags
}

module "documents" {
  source        = "../s3"
  name          = local.bucket_name
  force_destroy = !var.deletion_protection
  tags          = local.tags
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
  callback_urls              = var.enable_https ? ["https://${local.auth_domain}/auth/callback"] : ["http://${local.auth_domain}/auth/callback"]
  logout_urls                = var.enable_https ? ["https://${local.auth_domain}/login"] : ["http://${local.auth_domain}/login"]
  deletion_protection        = var.deletion_protection
  tags                       = local.tags
}

module "kubernetes" {
  source                 = "../kubernetes"
  name                   = local.name
  kubernetes_version     = var.kubernetes_version
  private_subnet_ids     = module.vpc.private_subnet_ids
  security_group_id      = module.vpc.kubernetes_security_group_id
  cluster_role_arn       = module.iam.eks_cluster_role_arn
  node_role_arn          = module.iam.eks_node_role_arn
  general_instance_types = var.general_instance_types
  qdrant_instance_types  = var.qdrant_instance_types
  gpu_instance_types     = var.gpu_instance_types
  general_desired_size   = var.general_desired_size
  qdrant_desired_size    = var.qdrant_desired_size
  gpu_desired_size       = var.gpu_desired_size
  tags                   = local.tags
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
