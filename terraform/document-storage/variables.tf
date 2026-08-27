variable "aws_region" {
  description = "AWS Region in which to create the document bucket and application role."
  type        = string
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name for canonical document objects."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be a valid 3-63 character lowercase S3 bucket name."
  }
}

variable "app_origins" {
  description = "Browser origins allowed to make direct presigned POST uploads."
  type        = list(string)

  validation {
    condition     = length(var.app_origins) > 0
    error_message = "Provide at least one application origin."
  }
}

variable "force_destroy" {
  description = "Allow Terraform to delete a non-empty bucket. Keep false outside disposable tests."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags added to all supported resources."
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Project   = "rag-knowledge-platform"
    Phase     = "8"
  }
}
