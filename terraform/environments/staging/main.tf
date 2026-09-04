locals {
  tags = merge(var.tags, {
    Project = "rag-platform", Environment = var.environment, ManagedBy = "Terraform"
  })
}
module "platform" {
  source = "../../modules/platform"

  environment                = var.environment
  aws_region                 = var.aws_region
  availability_zones         = var.availability_zones
  vpc_cidr                   = var.vpc_cidr
  public_subnet_cidrs        = var.public_subnet_cidrs
  private_subnet_cidrs       = var.private_subnet_cidrs
  single_nat_gateway         = var.single_nat_gateway
  enable_https               = var.enable_https
  domain_name                = var.domain_name
  hosted_zone_id             = var.hosted_zone_id
  github_repository          = var.github_repository
  github_oidc_subject_prefix = var.github_oidc_subject_prefix
  github_oidc_provider_arn   = var.github_oidc_provider_arn
  state_bucket_arn           = var.state_bucket_arn
  state_kms_key_arn          = var.state_kms_key_arn
  alert_email_addresses      = var.alert_email_addresses
  kubernetes_version         = var.kubernetes_version
  general_instance_types     = var.general_instance_types
  qdrant_instance_types      = var.qdrant_instance_types
  ingestion_instance_types   = var.ingestion_instance_types
  gpu_instance_types         = var.gpu_instance_types
  general_desired_size       = var.general_desired_size
  qdrant_desired_size        = var.qdrant_desired_size
  ingestion_desired_size     = var.ingestion_desired_size
  gpu_desired_size           = var.gpu_desired_size
  aurora_instance_class      = var.aurora_instance_class
  aurora_instance_count      = var.aurora_instance_count
  deletion_protection        = var.deletion_protection
  tags                       = local.tags
}
