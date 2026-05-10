# =============================================================================
# Provider configuration
# Provider mặc định: ap-southeast-1 (Singapore)
# Provider alias us-east-1: dành cho ACM certificate CloudFront (khi enable_cloudfront = true)
# =============================================================================

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# Provider us-east-1 cho ACM certificate CloudFront (bắt buộc phải ở us-east-1)
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }
}
