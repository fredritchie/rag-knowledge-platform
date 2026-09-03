variable "name" { type = string }
variable "domain_name" { type = string }
variable "hosted_zone_id" { type = string }
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
