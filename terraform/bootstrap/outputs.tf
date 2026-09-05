output "state_bucket_name" { value = aws_s3_bucket.state.id }
output "state_bucket_arn" { value = aws_s3_bucket.state.arn }
output "state_kms_key_arn" { value = aws_kms_key.state.arn }
output "github_oidc_provider_arn" {
  value = local.github_oidc_provider_arn
}

output "terraform_deploy_role_arn" {
  description = "Role assumed by the protected GitHub environment for Terraform deployment."
  value       = aws_iam_role.terraform_deploy.arn
}

output "terraform_deploy_role_arns" {
  description = "Terraform deployment role ARN for each protected GitHub environment."
  value = merge(
    { (var.terraform_deploy_environment) = aws_iam_role.terraform_deploy.arn },
    { for environment, role in aws_iam_role.additional_terraform_deploy : environment => role.arn }
  )
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
