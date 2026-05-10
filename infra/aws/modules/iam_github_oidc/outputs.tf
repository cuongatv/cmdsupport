# =============================================================================
# IAM GitHub OIDC module — outputs
# =============================================================================

output "oidc_provider_arn" {
  description = "ARN của GitHub OIDC provider"
  value       = aws_iam_openid_connect_provider.github.arn
}

output "github_actions_role_arn" {
  description = "ARN của IAM role cho GitHub Actions"
  value       = aws_iam_role.github_actions.arn
}

output "github_actions_role_name" {
  description = "Tên IAM role cho GitHub Actions"
  value       = aws_iam_role.github_actions.name
}
