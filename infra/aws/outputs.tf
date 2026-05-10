# =============================================================================
# Root outputs
# =============================================================================

# ─── Networking ──────────────────────────────────────────────────────────────

output "vpc_id" {
  description = "VPC ID"
  value       = module.network.vpc_id
}

# ─── Data tier ───────────────────────────────────────────────────────────────

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host:port)"
  value       = module.data.rds_endpoint
}

output "redis_endpoint" {
  description = "ElastiCache endpoint"
  value       = module.data.redis_endpoint
}

output "s3_bucket_name" {
  description = "S3 bucket cho file uploads"
  value       = module.data.s3_bucket_name
}

# ─── Compute ─────────────────────────────────────────────────────────────────

output "alb_dns_name" {
  description = "DNS name của Application Load Balancer"
  value       = module.compute.alb_dns_name
}

output "ecr_backend_url" {
  description = "ECR repository URL cho backend"
  value       = module.compute.ecr_backend_url
}

output "ecr_frontend_url" {
  description = "ECR repository URL cho frontend"
  value       = module.compute.ecr_frontend_url
}

output "ecs_cluster_name" {
  description = "Tên ECS cluster"
  value       = module.compute.ecs_cluster_name
}

# ─── Edge / DNS ──────────────────────────────────────────────────────────────

output "domain_apex" {
  description = "URL apex domain"
  value       = "https://${var.domain_name}"
}

output "domain_api" {
  description = "URL API domain"
  value       = "https://api.${var.domain_name}"
}

output "route53_name_servers" {
  description = "Name servers — trỏ từ registrar về đây"
  value       = module.edge.route53_zone_name_servers
}

# ─── CI/CD ───────────────────────────────────────────────────────────────────

output "github_actions_role_arn" {
  description = "ARN IAM role cho GitHub Actions OIDC"
  value       = module.iam_github_oidc.github_actions_role_arn
}
