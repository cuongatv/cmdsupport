# =============================================================================
# Edge module — outputs
# =============================================================================

output "acm_certificate_arn" {
  description = "ARN của ACM certificate (regional, cho ALB)"
  value       = aws_acm_certificate.regional.arn
}

output "acm_certificate_validated_arn" {
  description = "ARN của ACM certificate sau khi validate xong"
  value       = aws_acm_certificate_validation.regional.certificate_arn
}

output "route53_zone_id" {
  description = "Route53 hosted zone ID"
  value       = data.aws_route53_zone.main.zone_id
}

output "route53_zone_name_servers" {
  description = "Name servers của hosted zone"
  value       = data.aws_route53_zone.main.name_servers
}
