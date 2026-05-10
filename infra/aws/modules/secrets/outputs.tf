# =============================================================================
# Secrets module — outputs
# =============================================================================

output "secret_key_arn" {
  description = "ARN của secret SECRET_KEY trong Secrets Manager"
  value       = aws_secretsmanager_secret.secret_key.arn
}

output "db_password_arn" {
  description = "ARN của secret DB password trong Secrets Manager"
  value       = aws_secretsmanager_secret.db_password.arn
}

output "db_password" {
  description = "Database master password (để truyền cho module data)"
  value       = random_password.db_password.result
  sensitive   = true
}

output "cors_origins_arn" {
  description = "ARN của SSM parameter CORS origins"
  value       = aws_ssm_parameter.cors_origins.arn
}

output "next_public_api_url_arn" {
  description = "ARN của SSM parameter NEXT_PUBLIC_API_URL"
  value       = aws_ssm_parameter.next_public_api_url.arn
}
