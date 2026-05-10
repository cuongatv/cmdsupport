# =============================================================================
# Edge module — ACM Certificate, Route53 DNS, CloudFront (optional)
# =============================================================================

# ─── Route 53 Hosted Zone (data lookup) ──────────────────────────────────────
# Hosted zone phải được tạo trước và NS records trỏ về từ registrar.
# Nếu chưa có, tạo thủ công: aws route53 create-hosted-zone --name cmdsupport.com

data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# ─── ACM Certificate (ap-southeast-1) cho ALB ───────────────────────────────

resource "aws_acm_certificate" "regional" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"

  tags = {
    Name = "${var.name_prefix}-cert-regional"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# DNS validation records
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.regional.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 300
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main.zone_id
}

resource "aws_acm_certificate_validation" "regional" {
  certificate_arn         = aws_acm_certificate.regional.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

# ─── DNS Records ─────────────────────────────────────────────────────────────
# Trỏ apex + www + api về ALB (hoặc CloudFront nếu enable)

resource "aws_route53_record" "apex" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = var.alb_dns_name
    zone_id                = var.alb_zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "www" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = var.alb_dns_name
    zone_id                = var.alb_zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = var.alb_dns_name
    zone_id                = var.alb_zone_id
    evaluate_target_health = true
  }
}

# ─── CloudFront (optional — mặc định OFF cho pilot) ─────────────────────────
# Khi enable_cloudfront = true, cần thêm:
# 1. ACM certificate ở us-east-1 (provider alias)
# 2. CloudFront distribution
# 3. Cập nhật DNS records trỏ về CloudFront thay vì ALB
#
# Để triển khai: set enable_cloudfront = true và uncomment phần dưới,
# hoặc tạo resource với count = var.enable_cloudfront ? 1 : 0
# Hiện tại giữ đơn giản cho pilot — ALB serve trực tiếp HTTPS.
