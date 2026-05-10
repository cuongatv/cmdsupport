# =============================================================================
# Secrets module — variables
# =============================================================================

variable "name_prefix" {
  description = "Prefix cho resource naming"
  type        = string
}

variable "environment" {
  description = "Tên môi trường"
  type        = string
}

variable "domain_name" {
  description = "Tên miền chính"
  type        = string
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
