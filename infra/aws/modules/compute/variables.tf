# =============================================================================
# Compute module — variables
# =============================================================================

variable "name_prefix" {
  description = "Prefix cho resource naming"
  type        = string
}

variable "environment" {
  description = "Tên môi trường"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "domain_name" {
  description = "Tên miền chính"
  type        = string
}

# ─── Networking ──────────────────────────────────────────────────────────────

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs cho ALB"
  type        = list(string)
}

variable "private_app_subnet_ids" {
  description = "Private app subnet IDs cho ECS tasks"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group ID cho ALB"
  type        = string
}

variable "ecs_security_group_id" {
  description = "Security group ID cho ECS tasks (api + frontend)"
  type        = string
}

variable "worker_security_group_id" {
  description = "Security group ID cho worker tasks"
  type        = string
}

# ─── ACM ─────────────────────────────────────────────────────────────────────

variable "acm_certificate_arn" {
  description = "ARN của ACM certificate cho ALB HTTPS listener"
  type        = string
}

# ─── Secrets/Config ARNs ────────────────────────────────────────────────────

variable "secret_key_arn" {
  description = "ARN Secrets Manager — SECRET_KEY"
  type        = string
}

variable "db_password_arn" {
  description = "ARN Secrets Manager — DB password"
  type        = string
}

variable "cors_origins_arn" {
  description = "ARN SSM Parameter — CORS_ORIGINS"
  type        = string
}

variable "next_public_api_url_arn" {
  description = "ARN SSM Parameter — NEXT_PUBLIC_API_URL"
  type        = string
}

# ─── Data tier info ──────────────────────────────────────────────────────────

variable "rds_address" {
  description = "RDS PostgreSQL hostname"
  type        = string
}

variable "rds_port" {
  description = "RDS PostgreSQL port"
  type        = number
}

variable "rds_db_name" {
  description = "RDS database name"
  type        = string
}

variable "redis_endpoint" {
  description = "ElastiCache endpoint address"
  type        = string
}

variable "redis_port" {
  description = "ElastiCache port"
  type        = number
}

variable "s3_bucket_name" {
  description = "S3 bucket name"
  type        = string
}

variable "s3_bucket_arn" {
  description = "S3 bucket ARN"
  type        = string
}

# ─── Task sizing ─────────────────────────────────────────────────────────────

variable "api_cpu" {
  description = "CPU units cho cmd-api"
  type        = number
}

variable "api_memory" {
  description = "Memory (MB) cho cmd-api"
  type        = number
}

variable "worker_cpu" {
  description = "CPU units cho workers"
  type        = number
}

variable "worker_memory" {
  description = "Memory (MB) cho workers"
  type        = number
}

variable "frontend_cpu" {
  description = "CPU units cho frontend"
  type        = number
}

variable "frontend_memory" {
  description = "Memory (MB) cho frontend"
  type        = number
}

variable "api_desired_count" {
  description = "Số task cmd-api"
  type        = number
}

variable "worker_desired_count" {
  description = "Số task worker"
  type        = number
}

variable "frontend_desired_count" {
  description = "Số task frontend"
  type        = number
}

variable "image_tag_api" {
  description = "Image tag cho backend"
  type        = string
}

variable "image_tag_frontend" {
  description = "Image tag cho frontend"
  type        = string
}

variable "log_retention_days" {
  description = "Số ngày giữ log"
  type        = number
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
