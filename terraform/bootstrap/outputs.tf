output "state_bucket_name" { value = aws_s3_bucket.state.id }
output "state_bucket_arn" { value = aws_s3_bucket.state.arn }
output "state_kms_key_arn" { value = aws_kms_key.state.arn }
output "github_oidc_provider_arn" {
  value = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : var.existing_github_oidc_provider_arn
}

output "backend_hcl_template" {
  value = <<-EOT
    bucket       = "${aws_s3_bucket.state.id}"
    region       = "${var.aws_region}"
    kms_key_id   = "${aws_kms_key.state.arn}"
    encrypt      = true
    use_lockfile = true
  EOT
}
