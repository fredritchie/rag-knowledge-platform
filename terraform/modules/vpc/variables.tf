variable "name" { type = string }
variable "vpc_cidr" { type = string }
variable "availability_zones" {
  type = list(string)
  validation {
    condition     = length(var.availability_zones) == 3
    error_message = "Exactly three availability zones are required."
  }
}
variable "public_subnet_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.public_subnet_cidrs) == 3
    error_message = "Exactly three public subnet CIDRs are required."
  }
}
variable "private_subnet_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.private_subnet_cidrs) == 3
    error_message = "Exactly three private subnet CIDRs are required."
  }
}
variable "single_nat_gateway" {
  type        = bool
  default     = false
  description = "Use one NAT gateway to reduce non-production cost; production should use one per AZ."
}
variable "alb_ingress_port" {
  type    = number
  default = 443
}
variable "alb_ingress_prefix_list_id" {
  type        = string
  default     = null
  nullable    = true
  description = "Optional AWS-managed prefix list allowed to reach the ALB instead of the public internet."
}
variable "flow_log_retention_days" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
