# =============================================================================
# Network module — variables
# =============================================================================

variable "name_prefix" {
  description = "Prefix cho resource naming"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block cho VPC"
  type        = string
}

variable "azs" {
  description = "Danh sách Availability Zones"
  type        = list(string)
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default     = {}
}
