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
variable "tags" {
  type    = map(string)
  default = { Project = "rag-platform", ManagedBy = "Terraform", Component = "state" }
}
