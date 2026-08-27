output "user_pool_id" {
  value       = aws_cognito_user_pool.this.id
  description = "Cognito User Pool ID."
}

output "app_client_id" {
  value       = aws_cognito_user_pool_client.web.id
  description = "Browser application client ID; use as RAG__AUTH__AUDIENCE."
}

output "issuer" {
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
  description = "Use as RAG__AUTH__ISSUER."
}

output "jwks_url" {
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.this.id}/.well-known/jwks.json"
  description = "Use as RAG__AUTH__JWKS_URL if you choose to set it explicitly."
}

output "hosted_ui_base_url" {
  value       = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${var.aws_region}.amazoncognito.com"
  description = "Base URL for the Cognito hosted UI OAuth endpoints."
}
