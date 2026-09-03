variable "aws_region" { type = string }
variable "name" { type = string }
variable "bucket_arn" { type = string }
variable "queue_arn" { type = string }
variable "queue_kms_key_arn" { type = string }
variable "worker_role_name" { type = string }
variable "secret_name" { type = string }
variable "canonical_prefix" {
  type    = string
  default = "tenants/*/drive/*"
}
variable "recovery_window_in_days" {
  type    = number
  default = 30
}
variable "tags" {
  type = map(string)
  default = {
    ManagedBy = "Terraform"
    Project   = "rag-knowledge-platform"
    Phase     = "10"
  }
}
