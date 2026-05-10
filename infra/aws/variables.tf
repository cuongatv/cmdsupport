# =============================================================================
# Input variables — root module
# =============================================================================

# ─── Chung ───────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region triển khai"
  type        = string
  default     = "ap-southeast-1"
}

variable "environment" {
  description = "Tên môi trường: pilot, staging, prod"
  type        = string
  default     = "pilot"

  validation {
    condition     = contains(["pilot", "staging", "prod"], var.environment)
    error_message = "environment phải là pilot, staging, hoặc prod."
  }
}

variable "domain_name" {
  description = "Tên miền chính (apex)"
  type        = string
  default     = "cmdsupport.com"
}

variable "tags_extra" {
  description = "Tags bổ sung (merge vào common_tags)"
  type        = map(string)
  default     = {}
}

# ─── Networking ──────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "CIDR block cho VPC"
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "Số Availability Zones sử dụng"
  type        = number
  default     = 2
}

# ─── Database ────────────────────────────────────────────────────────────────

variable "db_instance_class" {
  description = "RDS instance class (pilot: db.t4g.medium, prod: db.r6g.large)"
  type        = string
  default     = "db.t4g.medium"
}

variable "db_multi_az" {
  description = "Bật Multi-AZ cho RDS (true cho prod)"
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "Bật deletion protection cho RDS"
  type        = bool
  default     = true
}

variable "db_allocated_storage" {
  description = "Dung lượng storage khởi tạo (GB)"
  type        = number
  default     = 50
}

variable "db_max_allocated_storage" {
  description = "Dung lượng storage tối đa cho autoscaling (GB)"
  type        = number
  default     = 200
}

# ─── Cache ───────────────────────────────────────────────────────────────────

variable "redis_node_type" {
  description = "ElastiCache node type (fallback khi không dùng serverless)"
  type        = string
  default     = "cache.t4g.micro"
}

variable "use_serverless_redis" {
  description = "Dùng ElastiCache Serverless (Valkey). Nếu false → dùng node-based Redis OSS"
  type        = bool
  default     = true
}

# ─── Compute (ECS) ──────────────────────────────────────────────────────────

variable "api_desired_count" {
  description = "Số task mong muốn cho cmd-api"
  type        = number
  default     = 1
}

variable "worker_desired_count" {
  description = "Số task mong muốn cho cmd-worker và cmd-worker-skills"
  type        = number
  default     = 1
}

variable "frontend_desired_count" {
  description = "Số task mong muốn cho cmd-frontend"
  type        = number
  default     = 1
}

variable "api_cpu" {
  description = "CPU units cho cmd-api task (1 vCPU = 1024)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Memory (MB) cho cmd-api task"
  type        = number
  default     = 1024
}

variable "worker_cpu" {
  description = "CPU units cho worker tasks"
  type        = number
  default     = 512
}

variable "worker_memory" {
  description = "Memory (MB) cho worker tasks"
  type        = number
  default     = 1024
}

variable "frontend_cpu" {
  description = "CPU units cho cmd-frontend task"
  type        = number
  default     = 512
}

variable "frontend_memory" {
  description = "Memory (MB) cho cmd-frontend task"
  type        = number
  default     = 1024
}

variable "image_tag_api" {
  description = "Image tag cho backend (api + worker). Lần đầu dùng 'bootstrap'"
  type        = string
  default     = "bootstrap"
}

variable "image_tag_frontend" {
  description = "Image tag cho frontend. Lần đầu dùng 'bootstrap'"
  type        = string
  default     = "bootstrap"
}

# ─── Logging ─────────────────────────────────────────────────────────────────

variable "log_retention_days" {
  description = "Số ngày giữ log trong CloudWatch"
  type        = number
  default     = 30
}

# ─── Edge / CDN ──────────────────────────────────────────────────────────────

variable "enable_cloudfront" {
  description = "Bật CloudFront distribution (mặc định false cho pilot)"
  type        = bool
  default     = false
}

# ─── CI/CD ───────────────────────────────────────────────────────────────────

variable "github_repo" {
  description = "GitHub repo dạng OWNER/REPO cho OIDC trust (vd: myorg/cmd-support)"
  type        = string
  default     = "ORG/cmd-support"
}

# ─── Monitoring ──────────────────────────────────────────────────────────────

variable "alarm_email" {
  description = "Email nhận SNS alarm (để trống nếu chưa cần)"
  type        = string
  default     = ""
}
