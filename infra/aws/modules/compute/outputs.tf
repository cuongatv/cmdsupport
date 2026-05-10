# =============================================================================
# Compute module — outputs
# =============================================================================

output "alb_dns_name" {
  description = "DNS name của ALB"
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "Hosted zone ID của ALB (cho Route53 alias)"
  value       = aws_lb.this.zone_id
}

output "alb_arn" {
  description = "ARN của ALB (cho WAF association)"
  value       = aws_lb.this.arn
}

output "ecr_backend_url" {
  description = "ECR repository URL cho backend"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  description = "ECR repository URL cho frontend"
  value       = aws_ecr_repository.frontend.repository_url
}

output "ecs_cluster_name" {
  description = "Tên ECS cluster"
  value       = aws_ecs_cluster.this.name
}

output "ecs_cluster_arn" {
  description = "ARN ECS cluster"
  value       = aws_ecs_cluster.this.arn
}

output "api_service_name" {
  description = "Tên ECS service api"
  value       = aws_ecs_service.api.name
}

output "frontend_service_name" {
  description = "Tên ECS service frontend"
  value       = aws_ecs_service.frontend.name
}

output "ecs_execution_role_arn" {
  description = "ARN ECS task execution role"
  value       = aws_iam_role.ecs_execution.arn
}

output "ecr_backend_arn" {
  description = "ARN ECR backend repository"
  value       = aws_ecr_repository.backend.arn
}

output "ecr_frontend_arn" {
  description = "ARN ECR frontend repository"
  value       = aws_ecr_repository.frontend.arn
}
