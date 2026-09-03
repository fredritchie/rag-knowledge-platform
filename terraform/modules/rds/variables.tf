variable "name" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "security_group_id" { type = string }
variable "engine_version" {
  type    = string
  default = "16.14"
}
variable "instance_class" {
  type    = string
  default = "db.r6g.large"
}
variable "instance_count" {
  type    = number
  default = 2
}
variable "backup_retention_days" {
  type    = number
  default = 14
}
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "skip_final_snapshot" {
  type    = bool
  default = false
}
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
