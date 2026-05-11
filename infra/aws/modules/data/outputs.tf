# =============================================================================
# Data module — outputs
# =============================================================================

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host:port)"
  value       = aws_db_instance.this.endpoint
}

output "rds_address" {
  description = "RDS PostgreSQL hostname"
  value       = aws_db_instance.this.address
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.this.port
}

output "rds_db_name" {
  description = "Tên database"
  value       = aws_db_instance.this.db_name
}

output "redis_endpoint" {
  description = "ElastiCache endpoint"
  value = var.use_serverless_redis ? (
    length(aws_elasticache_serverless_cache.valkey) > 0 ? aws_elasticache_serverless_cache.valkey[0].endpoint[0].address : ""
    ) : (
    length(aws_elasticache_cluster.redis) > 0 ? aws_elasticache_cluster.redis[0].cache_nodes[0].address : ""
  )
}

output "redis_port" {
  description = "ElastiCache port"
  value = var.use_serverless_redis ? (
    length(aws_elasticache_serverless_cache.valkey) > 0 ? aws_elasticache_serverless_cache.valkey[0].endpoint[0].port : 6379
  ) : 6379
}

output "s3_bucket_name" {
  description = "Tên S3 bucket lưu files"
  value       = aws_s3_bucket.files.id
}

output "s3_bucket_arn" {
  description = "ARN của S3 bucket"
  value       = aws_s3_bucket.files.arn
}
