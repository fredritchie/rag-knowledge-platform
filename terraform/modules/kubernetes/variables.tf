variable "name" { type = string }
variable "kubernetes_version" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "security_group_id" { type = string }
variable "cluster_role_arn" { type = string }
variable "node_role_arn" { type = string }
variable "general_instance_types" {
  type    = list(string)
  default = ["m7i.large"]
}
variable "qdrant_instance_types" {
  type    = list(string)
  default = ["r7i.xlarge"]
}
variable "ingestion_instance_types" {
  type    = list(string)
  default = ["c7i.large"]
}
variable "gpu_instance_types" {
  type    = list(string)
  default = ["g5.xlarge"]
}
variable "general_desired_size" {
  type    = number
  default = 2
}
variable "qdrant_desired_size" {
  type    = number
  default = 3
}
variable "ingestion_desired_size" {
  type    = number
  default = 1
}
variable "gpu_desired_size" {
  type    = number
  default = 0
}
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "tags" {
  type    = map(string)
  default = {}
}
