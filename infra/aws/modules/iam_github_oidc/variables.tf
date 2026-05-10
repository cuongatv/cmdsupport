# =============================================================================
# IAM GitHub OIDC module — variables
# =============================================================================

variable "name_prefix" {
  description = "Prefix cho resource naming"
  type        = string
}

variable "github_repo" {
  description = "GitHub repo dạng OWNER/REPO"
  type        = string
}

variable "ecr_backend_arn" {
  description = "ARN ECR backend repository"
  type        = string
}

variable "ecr_frontend_arn" {
  description = "ARN ECR frontend repository"
  type        = string
}

variable "ecs_cluster_arn" {
  description = "ARN ECS cluster"
  type        = string
}

variable "ecs_cluster_name" {
  description = "Tên ECS cluster"
  type        = string
}

variable "account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
