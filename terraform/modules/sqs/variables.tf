variable "name" { type = string }
variable "source_bucket_arn" { type = string }
variable "visibility_timeout_seconds" {
  type    = number
  default = 900
}
variable "max_receive_count" {
  type    = number
  default = 5
}
variable "alarm_actions" {
  type    = list(string)
  default = []
}
variable "tags" {
  type    = map(string)
  default = {}
}
