# =============================================================================
# Root module — Gọi các sub-modules
# =============================================================================
#
# Thứ tự dependency:
#   1. network   → VPC, subnets, SGs
#   2. secrets   → Secrets Manager, SSM (không phụ thuộc network)
#   3. data      → RDS, ElastiCache, S3 (cần network + secrets)
#   4. edge      → ACM, Route53 (cần ALB DNS — nhưng ACM cert cần trước ALB listener)
#   5. compute   → ECR, ECS, ALB (cần network + data + secrets + ACM cert)
#   6. waf       → WAFv2 (cần ALB ARN)
#   7. iam_oidc  → GitHub OIDC (cần ECR + ECS ARNs)
#
# Lưu ý: edge module tạo ACM cert trước, compute module dùng cert cho ALB,
# rồi edge module dùng ALB DNS cho Route53 records.
# Để tránh circular dependency: edge module nhận alb_dns_name từ compute.
# Giải pháp: tách ACM cert ra edge, truyền cert ARN cho compute,
# compute output ALB DNS, edge dùng cho Route53.
# =============================================================================

# ─── 1. Network ──────────────────────────────────────────────────────────────

module "network" {
  source = "./modules/network"

  name_prefix = local.name_prefix
  vpc_cidr    = var.vpc_cidr
  azs         = local.azs
  tags        = local.common_tags
}

# ─── 2. Secrets ──────────────────────────────────────────────────────────────

module "secrets" {
  source = "./modules/secrets"

  name_prefix = local.name_prefix
  environment = var.environment
  domain_name = var.domain_name
  tags        = local.common_tags
}

# ─── 3. Data ─────────────────────────────────────────────────────────────────

module "data" {
  source = "./modules/data"

  name_prefix             = local.name_prefix
  environment             = var.environment
  vpc_id                  = module.network.vpc_id
  private_data_subnet_ids = module.network.private_data_subnet_ids
  db_security_group_id    = module.network.db_security_group_id
  redis_security_group_id = module.network.redis_security_group_id

  db_instance_class        = var.db_instance_class
  db_multi_az              = var.db_multi_az
  db_deletion_protection   = var.db_deletion_protection
  db_allocated_storage     = var.db_allocated_storage
  db_max_allocated_storage = var.db_max_allocated_storage
  db_password_secret_arn   = module.secrets.db_password_arn
  db_password              = module.secrets.db_password

  use_serverless_redis = var.use_serverless_redis
  redis_node_type      = var.redis_node_type

  tags = local.common_tags
}

# ─── 4. Edge (ACM + Route53) ────────────────────────────────────────────────
# Tạo ACM cert trước. Route53 records cần ALB DNS từ compute module.

module "edge" {
  source = "./modules/edge"

  name_prefix       = local.name_prefix
  domain_name       = var.domain_name
  alb_dns_name      = module.compute.alb_dns_name
  alb_zone_id       = module.compute.alb_zone_id
  enable_cloudfront = var.enable_cloudfront
  tags              = local.common_tags
}

# ─── 5. Compute ──────────────────────────────────────────────────────────────

module "compute" {
  source = "./modules/compute"

  name_prefix = local.name_prefix
  environment = var.environment
  aws_region  = var.aws_region
  account_id  = local.account_id
  domain_name = var.domain_name

  # Networking
  vpc_id                   = module.network.vpc_id
  public_subnet_ids        = module.network.public_subnet_ids
  private_app_subnet_ids   = module.network.private_app_subnet_ids
  alb_security_group_id    = module.network.alb_security_group_id
  ecs_security_group_id    = module.network.ecs_security_group_id
  worker_security_group_id = module.network.worker_security_group_id

  # ACM cert
  acm_certificate_arn = module.edge.acm_certificate_validated_arn

  # Secrets
  secret_key_arn          = module.secrets.secret_key_arn
  db_password_arn         = module.secrets.db_password_arn
  cors_origins_arn        = module.secrets.cors_origins_arn
  next_public_api_url_arn = module.secrets.next_public_api_url_arn

  # Data tier
  rds_address    = module.data.rds_address
  rds_port       = module.data.rds_port
  rds_db_name    = module.data.rds_db_name
  redis_endpoint = module.data.redis_endpoint
  redis_port     = module.data.redis_port
  s3_bucket_name = module.data.s3_bucket_name
  s3_bucket_arn  = module.data.s3_bucket_arn

  # Task sizing
  api_cpu         = var.api_cpu
  api_memory      = var.api_memory
  worker_cpu      = var.worker_cpu
  worker_memory   = var.worker_memory
  frontend_cpu    = var.frontend_cpu
  frontend_memory = var.frontend_memory

  # Desired counts
  api_desired_count      = var.api_desired_count
  worker_desired_count   = var.worker_desired_count
  frontend_desired_count = var.frontend_desired_count

  # Image tags
  image_tag_api      = var.image_tag_api
  image_tag_frontend = var.image_tag_frontend

  # Logging
  log_retention_days = var.log_retention_days

  tags = local.common_tags
}

# ─── 6. WAF ──────────────────────────────────────────────────────────────────

module "waf" {
  source = "./modules/waf"

  name_prefix = local.name_prefix
  alb_arn     = module.compute.alb_arn
  tags        = local.common_tags
}

# ─── 7. GitHub Actions OIDC ─────────────────────────────────────────────────

module "iam_github_oidc" {
  source = "./modules/iam_github_oidc"

  name_prefix      = local.name_prefix
  github_repo      = var.github_repo
  ecr_backend_arn  = module.compute.ecr_backend_arn
  ecr_frontend_arn = module.compute.ecr_frontend_arn
  ecs_cluster_arn  = module.compute.ecs_cluster_arn
  ecs_cluster_name = module.compute.ecs_cluster_name
  account_id       = local.account_id
  aws_region       = var.aws_region
  tags             = local.common_tags
}
