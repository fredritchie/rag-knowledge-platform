variable "environment" { type = string }
variable "aws_region" { type = string }
variable "availability_zones" { type = list(string) }
variable "vpc_cidr" { type = string }
variable "public_subnet_cidrs" { type = list(string) }
variable "private_subnet_cidrs" { type = list(string) }
variable "single_nat_gateway" { type = bool }
variable "enable_https" { type = bool }
variable "domain_name" {
  type     = string
  nullable = true
}
variable "hosted_zone_id" {
  type     = string
  nullable = true
}
variable "github_repository" { type = string }
variable "github_oidc_subject_prefix" {
  type     = string
  default  = null
  nullable = true
}
variable "github_oidc_provider_arn" { type = string }
variable "state_bucket_arn" { type = string }
variable "state_kms_key_arn" { type = string }
variable "alert_email_addresses" { type = set(string) }
variable "kubernetes_version" { type = string }
variable "general_instance_types" { type = list(string) }
variable "qdrant_instance_types" { type = list(string) }
variable "ingestion_instance_types" { type = list(string) }
variable "gpu_instance_types" { type = list(string) }
variable "general_desired_size" { type = number }
variable "qdrant_desired_size" { type = number }
variable "ingestion_desired_size" { type = number }
variable "gpu_desired_size" { type = number }
variable "aurora_instance_class" { type = string }
variable "aurora_instance_count" { type = number }
variable "deletion_protection" { type = bool }
variable "drive_secret_arns" {
  type        = set(string)
  default     = []
  description = "Secrets Manager ARNs containing Google Drive OAuth credentials readable by sync workers."
}
variable "tags" {
  type    = map(string)
  default = {}
}
