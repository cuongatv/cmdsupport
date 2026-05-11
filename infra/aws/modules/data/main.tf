# =============================================================================
# Data module — RDS PostgreSQL 16, ElastiCache (Valkey serverless / Redis), S3
# =============================================================================

# ─── Random suffix cho S3 bucket ─────────────────────────────────────────────

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# ─── RDS PostgreSQL 16 ──────────────────────────────────────────────────────

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnet"
  subnet_ids = var.private_data_subnet_ids

  tags = {
    Name = "${var.name_prefix}-db-subnet-group"
  }
}

resource "aws_db_parameter_group" "pg16" {
  name   = "${var.name_prefix}-pg16-params"
  family = "postgres16"

  # Parameter group cho PostgreSQL 16
  # pgvector extension được RDS hỗ trợ sẵn — chỉ cần chạy CREATE EXTENSION vector từ migration

  tags = {
    Name = "${var.name_prefix}-pg16-params"
  }
}

resource "aws_db_instance" "this" {
  identifier = "${var.name_prefix}-postgres"

  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true # KMS default (aws/rds)

  db_name  = "cmd_support"
  username = "cmd_support_admin"
  password = var.db_password

  multi_az               = var.db_multi_az
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.db_security_group_id]
  parameter_group_name   = aws_db_parameter_group.pg16.name

  # Backup
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:30-sun:05:30"

  # Bảo vệ
  deletion_protection       = var.db_deletion_protection
  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${var.name_prefix}-final-snapshot" : null
  copy_tags_to_snapshot     = true

  # Performance Insights (miễn phí cho t4g)
  performance_insights_enabled = true

  tags = {
    Name = "${var.name_prefix}-postgres"
  }

  lifecycle {
    ignore_changes = [password]
  }
}

# ─── ElastiCache ─────────────────────────────────────────────────────────────

# Subnet group dùng chung cho cả serverless và node-based
resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-cache-subnet"
  subnet_ids = var.private_data_subnet_ids

  tags = {
    Name = "${var.name_prefix}-cache-subnet-group"
  }
}

# Option A: ElastiCache Serverless (Valkey)
resource "aws_elasticache_serverless_cache" "valkey" {
  count = var.use_serverless_redis ? 1 : 0

  engine = "valkey"
  name   = "${var.name_prefix}-valkey"

  cache_usage_limits {
    data_storage {
      maximum = 1 # GB — điều chỉnh theo nhu cầu
      unit    = "GB"
    }
    ecpu_per_second {
      maximum = 1000
    }
  }

  subnet_ids         = var.private_data_subnet_ids
  security_group_ids = [var.redis_security_group_id]

  tags = {
    Name = "${var.name_prefix}-valkey"
  }
}

# Option B: Node-based Redis OSS (fallback)
resource "aws_elasticache_cluster" "redis" {
  count = var.use_serverless_redis ? 0 : 1

  cluster_id      = "${var.name_prefix}-redis"
  engine          = "redis"
  engine_version  = "7.1"
  node_type       = var.redis_node_type
  num_cache_nodes = 1
  port            = 6379

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [var.redis_security_group_id]

  tags = {
    Name = "${var.name_prefix}-redis"
  }
}

# ─── S3 Bucket ───────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "files" {
  bucket = "cmd-support-files-${var.environment}-${random_id.bucket_suffix.hex}"

  tags = {
    Name = "cmd-support-files-${var.environment}"
  }
}

resource "aws_s3_bucket_versioning" "files" {
  bucket = aws_s3_bucket.files.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket = aws_s3_bucket.files.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
