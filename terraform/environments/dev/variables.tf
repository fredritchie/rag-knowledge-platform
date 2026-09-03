variable "environment" { type = string }
variable "aws_region" { type = string }
variable "availability_zones" { type = list(string) }
variable "vpc_cidr" { type = string }
variable "public_subnet_cidrs" { type = list(string) }
variable "private_subnet_cidrs" { type = list(string) }
variable "single_nat_gateway" {
  type    = bool
  default = false
}
variable "enable_https" {
  type    = bool
  default = true
}
variable "domain_name" {
  type     = string
  default  = null
  nullable = true
}
variable "hosted_zone_id" {
  type     = string
  default  = null
  nullable = true
}
variable "github_repository" { type = string }
variable "github_oidc_provider_arn" { type = string }
variable "state_bucket_arn" { type = string }
variable "state_kms_key_arn" { type = string }
variable "alert_email_addresses" {
  type    = set(string)
  default = []
}
variable "kubernetes_version" {
  type    = string
  default = "1.35"
}
variable "general_instance_types" {
  type    = list(string)
  default = ["m7i.large"]
}
variable "qdrant_instance_types" {
  type    = list(string)
  default = ["r7i.xlarge"]
}
variable "gpu_instance_types" {
  type    = list(string)
  default = ["g5.xlarge"]
}
variable "general_desired_size" {
  type    = number
  default = 2
}
variable "qdrant_desired_size" {
  type    = number
  default = 3
}
variable "gpu_desired_size" {
  type    = number
  default = 0
}
variable "aurora_instance_class" {
  type    = string
  default = "db.r6g.large"
}
variable "aurora_instance_count" {
  type    = number
  default = 2
}
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "tags" {
  type    = map(string)
  default = {}
}
