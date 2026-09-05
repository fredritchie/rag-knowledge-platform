variable "aws_region" { type = string }
variable "state_bucket_name" { type = string }
variable "create_github_oidc_provider" {
  type        = bool
  default     = true
  description = "Create the account-level GitHub Actions OIDC provider. Set false when one already exists."
}
variable "existing_github_oidc_provider_arn" {
  type        = string
  default     = null
  description = "Existing GitHub Actions OIDC provider ARN, required when creation is disabled."
  validation {
    condition     = var.create_github_oidc_provider || var.existing_github_oidc_provider_arn != null
    error_message = "existing_github_oidc_provider_arn is required when create_github_oidc_provider is false."
  }
}
variable "github_oidc_subject_prefix" {
  type        = string
  default     = "repo:fredritchie@130365973/rag-knowledge-platform@1342829048"
  description = "GitHub OIDC subject prefix, including customized organization and repository IDs when configured."
}
variable "terraform_deploy_environment" {
  type        = string
  default     = "dev"
  description = "Protected GitHub environment allowed to assume the Terraform deployment role."
}
variable "terraform_managed_name_prefix" {
  type        = string
  default     = "rag-platform-dev"
  description = "Name prefix of IAM roles and policies the Terraform deployment role may manage."
  validation {
    condition     = length(var.terraform_managed_name_prefix) >= 8 && !startswith("rag-platform-terraform-${var.terraform_deploy_environment}", "${var.terraform_managed_name_prefix}-")
    error_message = "The managed prefix must be specific and must not include the Terraform deployment role."
  }
}
variable "tags" {
  type    = map(string)
  default = { Project = "rag-platform", ManagedBy = "Terraform", Component = "state" }
}
