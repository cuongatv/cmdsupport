# =============================================================================
# WAF module — outputs
# =============================================================================

output "web_acl_arn" {
  description = "ARN của WAFv2 Web ACL"
  value       = aws_wafv2_web_acl.this.arn
}

output "web_acl_id" {
  description = "ID của WAFv2 Web ACL"
  value       = aws_wafv2_web_acl.this.id
}
