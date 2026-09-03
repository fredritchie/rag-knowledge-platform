variable "name" { type = string }
variable "force_destroy" {
  type    = bool
  default = false
}
variable "noncurrent_version_expiration_days" {
  type    = number
  default = 90
}
variable "tags" {
  type    = map(string)
  default = {}
}
