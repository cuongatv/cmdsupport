# =============================================================================
# Locals — naming convention và tags chuẩn
# =============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  # Prefix chuẩn cho resource naming: cmd-pilot, cmd-staging, cmd-prod
  name_prefix = "cmd-${var.environment}"

  # Account ID để dùng trong ARN
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  # Availability Zones
  azs = slice(
    ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"],
    0,
    var.az_count
  )

  # Tags chuẩn gắn vào mọi resource
  common_tags = merge(
    {
      Project     = "cmd-support"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags_extra
  )
}
