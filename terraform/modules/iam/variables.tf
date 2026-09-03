variable "name" { type = string }
variable "github_oidc_subject_prefix" { type = string }
variable "github_environment" { type = string }
variable "github_branch" {
  type    = string
  default = "main"
}
variable "github_oidc_provider_arn" { type = string }
variable "state_bucket_arn" { type = string }
variable "state_kms_key_arn" { type = string }
variable "sns_topic_arn" { type = string }
variable "alert_kms_key_arn" { type = string }
variable "ecr_repository_arns" { type = list(string) }
variable "callback_urls" { type = list(string) }
variable "logout_urls" { type = list(string) }
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "tags" {
  type    = map(string)
  default = {}
}
