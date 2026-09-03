# IAM and identity module

Creates EKS cluster/node roles, a least-privilege GitHub OIDC role for read-only drift plans, a protected Cognito user pool/client, and the runtime Secrets Manager container. Secret values are intentionally populated outside Terraform so they never enter state.
