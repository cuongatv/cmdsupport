# =============================================================================
# Secrets module — Secrets Manager + SSM Parameter Store
# =============================================================================

# ─── Random passwords ───────────────────────────────────────────────────────

resource "random_password" "secret_key" {
  length  = 64
  special = false # base64url-safe
}

resource "random_password" "db_password" {
  length           = 32
  special          = true
  override_special = "!#$%^&*()-_=+"
}

# ─── Secrets Manager ────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "secret_key" {
  name        = "cmd-support/${var.environment}/secret_key"
  description = "SECRET_KEY cho ung dung CMD Support (${var.environment})"

  tags = {
    Name = "${var.name_prefix}-secret-key"
  }
}

resource "aws_secretsmanager_secret_version" "secret_key" {
  secret_id     = aws_secretsmanager_secret.secret_key.id
  secret_string = random_password.secret_key.result

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "db_password" {
  name        = "cmd-support/${var.environment}/db_password"
  description = "Master password cho RDS PostgreSQL (${var.environment})"

  tags = {
    Name = "${var.name_prefix}-db-password"
  }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db_password.result

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ─── SSM Parameter Store ────────────────────────────────────────────────────

resource "aws_ssm_parameter" "cors_origins" {
  name        = "/cmd-support/${var.environment}/cors_origins"
  description = "CORS origins cho backend API"
  type        = "SecureString"
  value       = "https://${var.domain_name},https://www.${var.domain_name}"

  tags = {
    Name = "${var.name_prefix}-cors-origins"
  }
}

resource "aws_ssm_parameter" "next_public_api_url" {
  name        = "/cmd-support/${var.environment}/next_public_api_url"
  description = "Public API URL cho frontend"
  type        = "SecureString"
  value       = "https://api.${var.domain_name}"

  tags = {
    Name = "${var.name_prefix}-next-public-api-url"
  }
}
