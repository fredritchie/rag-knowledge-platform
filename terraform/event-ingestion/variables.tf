variable "aws_region" {
  description = "AWS Region containing the existing Phase 8 document bucket and EC2 worker."
  type        = string
}

variable "name" {
  description = "Unique name prefix for the EventBridge rule, SQS queues, KMS key, and alarm."
  type        = string
}

variable "bucket_name" {
  description = "Existing canonical Phase 8 S3 bucket name."
  type        = string
}

variable "bucket_arn" {
  description = "ARN of the existing canonical Phase 8 S3 bucket."
  type        = string
}

variable "worker_role_name" {
  description = "Existing EC2 IAM role name used by the API and ingestion workers."
  type        = string
}

variable "alarm_actions" {
  description = "Optional SNS topic or other CloudWatch alarm action ARNs."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to Phase 9 resources."
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Project   = "rag-knowledge-platform"
    Phase     = "9"
  }
}
