# =============================================================================
# Network module — outputs
# =============================================================================

output "vpc_id" {
  description = "ID của VPC"
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "CIDR block của VPC"
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "IDs của public subnets"
  value       = aws_subnet.public[*].id
}

output "private_app_subnet_ids" {
  description = "IDs của private app subnets (ECS Fargate)"
  value       = aws_subnet.private_app[*].id
}

output "private_data_subnet_ids" {
  description = "IDs của private data subnets (RDS, ElastiCache)"
  value       = aws_subnet.private_data[*].id
}

output "alb_security_group_id" {
  description = "Security group ID cho ALB"
  value       = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  description = "Security group ID cho ECS tasks"
  value       = aws_security_group.ecs.id
}

output "worker_security_group_id" {
  description = "Security group ID cho worker tasks"
  value       = aws_security_group.worker.id
}

output "db_security_group_id" {
  description = "Security group ID cho RDS"
  value       = aws_security_group.db.id
}

output "redis_security_group_id" {
  description = "Security group ID cho ElastiCache"
  value       = aws_security_group.redis.id
}
