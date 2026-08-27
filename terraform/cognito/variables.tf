variable "aws_region" {
  description = "AWS Region in which to create the Cognito user pool."
  type        = string
}

variable "name" {
  description = "Short, globally unique name for this authentication environment."
  type        = string
}

variable "callback_urls" {
  description = "OAuth callback URLs for the browser client."
  type        = list(string)
}

variable "logout_urls" {
  description = "OAuth logout URLs for the browser client."
  type        = list(string)
}

variable "deletion_protection" {
  description = "Set to ACTIVE outside ephemeral development environments."
  type        = string
  default     = "INACTIVE"

  validation {
    condition     = contains(["ACTIVE", "INACTIVE"], var.deletion_protection)
    error_message = "deletion_protection must be ACTIVE or INACTIVE."
  }
}

variable "test_users" {
  description = "Optional users to create. Passwords are deliberately not managed by Terraform."
  type = map(object({
    email     = string
    tenant_id = string
    groups    = optional(list(string), [])
  }))
  default = {}
}

variable "tags" {
  description = "Tags added to all supported AWS resources."
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Project   = "rag-knowledge-platform"
  }
}
