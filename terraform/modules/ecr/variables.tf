variable "name_prefix" { type = string }
variable "repositories" { type = set(string) }
variable "kms_key_arn" { type = string }
variable "force_delete" {
  type    = bool
  default = false
}
variable "tags" {
  type    = map(string)
  default = {}
}
