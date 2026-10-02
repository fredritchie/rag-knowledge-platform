variable "name" { type = string }
variable "upload_origins" {
  description = "Exact browser origins permitted to POST presigned uploads; empty disables CORS."
  type        = list(string)
  default     = []
  validation {
    condition = alltrue([
      for origin in var.upload_origins : can(regex("^https?://[^/*?#]+$", origin))
    ])
    error_message = "Upload origins must be HTTP(S) origins without wildcard, path, query or fragment."
  }
}
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
