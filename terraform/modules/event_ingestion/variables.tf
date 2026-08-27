variable "name" {
  type    = string
  default = "rag-ingestion"
}
variable "bucket_name" { type = string }
variable "bucket_arn" { type = string }
variable "enable_bucket_versioning" {
  type    = bool
  default = true
}
variable "object_prefix" {
  type    = string
  default = "tenants/"
}
variable "visibility_timeout_seconds" {
  type    = number
  default = 900
}
variable "message_retention_seconds" {
  type    = number
  default = 345600
}
variable "dlq_retention_seconds" {
  type    = number
  default = 1209600
}
variable "max_receive_count" {
  type    = number
  default = 5
}
variable "dlq_alarm_threshold" {
  type    = number
  default = 1
}
variable "alarm_actions" {
  type    = list(string)
  default = []
}
variable "kms_deletion_window_in_days" {
  type    = number
  default = 30

  validation {
    condition     = var.kms_deletion_window_in_days >= 7 && var.kms_deletion_window_in_days <= 30
    error_message = "kms_deletion_window_in_days must be between 7 and 30."
  }
}
variable "tags" {
  type    = map(string)
  default = {}
}
