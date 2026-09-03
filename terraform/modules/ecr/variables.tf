variable "name_prefix" { type = string }
variable "repositories" { type = set(string) }
variable "kms_key_arn" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
