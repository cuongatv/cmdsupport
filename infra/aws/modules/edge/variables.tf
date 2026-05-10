# =============================================================================
# Edge module — variables
# =============================================================================

variable "name_prefix" {
  description = "Prefix cho resource naming"
  type        = string
}

variable "domain_name" {
  description = "Tên miền apex (vd: cmdsupport.com)"
  type        = string
}

variable "alb_dns_name" {
  description = "DNS name của ALB"
  type        = string
}

variable "alb_zone_id" {
  description = "Hosted zone ID của ALB"
  type        = string
}

variable "enable_cloudfront" {
  description = "Bật CloudFront distribution"
  type        = bool
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
