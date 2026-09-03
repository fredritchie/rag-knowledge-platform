variable "name" { type = string }
variable "alert_email_addresses" {
  type    = set(string)
  default = []
}
variable "alb_arn_suffix" { type = string }
variable "rds_cluster_identifier" { type = string }
variable "eks_cluster_name" { type = string }
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
