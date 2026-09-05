variable "name" { type = string }
variable "enable_https" {
  type    = bool
  default = true
}
variable "domain_name" {
  type     = string
  default  = null
  nullable = true
}
variable "hosted_zone_id" {
  type     = string
  default  = null
  nullable = true
}
variable "certificate_arn" {
  type        = string
  default     = null
  nullable    = true
  description = "Existing ACM certificate ARN for externally managed DNS providers such as DuckDNS."
}
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "security_group_id" { type = string }
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "force_destroy_buckets" {
  type    = bool
  default = false
}
variable "waf_rate_limit" {
  type    = number
  default = 2000
}
variable "tags" {
  type    = map(string)
  default = {}
}
