# =============================================================================
# Data module — variables
# =============================================================================

variable "name_prefix" {
  description = "Prefix cho resource naming"
  type        = string
}

variable "environment" {
  description = "Tên môi trường"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_data_subnet_ids" {
  description = "Subnet IDs cho data tier (RDS, ElastiCache)"
  type        = list(string)
}

variable "db_security_group_id" {
  description = "Security group ID cho RDS"
  type        = string
}

variable "redis_security_group_id" {
  description = "Security group ID cho ElastiCache"
  type        = string
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
}

variable "db_multi_az" {
  description = "Bật Multi-AZ cho RDS"
  type        = bool
}

variable "db_deletion_protection" {
  description = "Bật deletion protection cho RDS"
  type        = bool
}

variable "db_allocated_storage" {
  description = "Dung lượng storage khởi tạo (GB)"
  type        = number
}

variable "db_max_allocated_storage" {
  description = "Dung lượng storage tối đa (GB)"
  type        = number
}

variable "db_password_secret_arn" {
  description = "ARN của Secrets Manager secret chứa DB password"
  type        = string
}

variable "db_password" {
  description = "Database master password"
  type        = string
  sensitive   = true
}

variable "use_serverless_redis" {
  description = "Dùng ElastiCache Serverless (Valkey)"
  type        = bool
}

variable "redis_node_type" {
  description = "ElastiCache node type (fallback khi không dùng serverless)"
  type        = string
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
