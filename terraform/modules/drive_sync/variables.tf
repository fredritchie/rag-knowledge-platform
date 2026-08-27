variable "name" {
  type    = string
  default = "rag-drive-sync"
}
variable "bucket_arn" { type = string }
variable "queue_arn" { type = string }
variable "queue_kms_key_arn" { type = string }
variable "secret_arns" { type = list(string) }
variable "canonical_prefix" {
  type    = string
  default = "tenants/*/drive/*"
}
variable "tags" {
  type    = map(string)
  default = {}
}
