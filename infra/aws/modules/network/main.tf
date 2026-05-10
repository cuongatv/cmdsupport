# =============================================================================
# Network module — VPC, Subnets, NAT, IGW, Route Tables, VPC Endpoints, SGs
# =============================================================================
#
# Subnet layout (10.20.0.0/16):
#   Public:       10.20.0.0/24, 10.20.1.0/24    (ALB, NAT GW)
#   Private App:  10.20.10.0/24, 10.20.11.0/24  (ECS Fargate)
#   Private Data: 10.20.20.0/24, 10.20.21.0/24  (RDS, ElastiCache — không route Internet)
#
# Pilot: 1 NAT Gateway (tiết kiệm). Prod: có thể tăng lên 2 NAT GW
# (xem comment bên dưới để mở rộng).
# =============================================================================

# ─── VPC ─────────────────────────────────────────────────────────────────────

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.name_prefix}-vpc"
  }
}

# ─── Internet Gateway ───────────────────────────────────────────────────────

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-igw"
  }
}

# ─── Subnets ────────────────────────────────────────────────────────────────

resource "aws_subnet" "public" {
  count = length(var.azs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index) # 10.20.0.0/24, 10.20.1.0/24
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.name_prefix}-public-${var.azs[count.index]}"
    Tier = "public"
  }
}

resource "aws_subnet" "private_app" {
  count = length(var.azs)

  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 10 + count.index) # 10.20.10.0/24, 10.20.11.0/24
  availability_zone = var.azs[count.index]

  tags = {
    Name = "${var.name_prefix}-private-app-${var.azs[count.index]}"
    Tier = "private-app"
  }
}

resource "aws_subnet" "private_data" {
  count = length(var.azs)

  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 20 + count.index) # 10.20.20.0/24, 10.20.21.0/24
  availability_zone = var.azs[count.index]

  tags = {
    Name = "${var.name_prefix}-private-data-${var.azs[count.index]}"
    Tier = "private-data"
  }
}

# ─── Elastic IP + NAT Gateway ───────────────────────────────────────────────
# Pilot: 1 NAT GW ở AZ đầu tiên. Để mở rộng thành 2 cho prod,
# thay count = 1 thành count = length(var.azs) và cập nhật route tables.

resource "aws_eip" "nat" {
  count  = 1 # Pilot: 1. Prod: length(var.azs)
  domain = "vpc"

  tags = {
    Name = "${var.name_prefix}-nat-eip-${count.index}"
  }
}

resource "aws_nat_gateway" "this" {
  count = 1 # Pilot: 1. Prod: length(var.azs)

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name = "${var.name_prefix}-nat-${count.index}"
  }

  depends_on = [aws_internet_gateway.this]
}

# ─── Route Tables ────────────────────────────────────────────────────────────

# Public route table — route 0.0.0.0/0 → IGW
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-rt-public"
  }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = length(var.azs)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Private app route table — route 0.0.0.0/0 → NAT GW
resource "aws_route_table" "private_app" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-rt-private-app"
  }
}

resource "aws_route" "private_app_nat" {
  route_table_id         = aws_route_table.private_app.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

resource "aws_route_table_association" "private_app" {
  count = length(var.azs)

  subnet_id      = aws_subnet.private_app[count.index].id
  route_table_id = aws_route_table.private_app.id
}

# Private data route table — KHÔNG có route ra Internet
resource "aws_route_table" "private_data" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-rt-private-data"
  }
}

resource "aws_route_table_association" "private_data" {
  count = length(var.azs)

  subnet_id      = aws_subnet.private_data[count.index].id
  route_table_id = aws_route_table.private_data.id
}

# ─── VPC Endpoints ──────────────────────────────────────────────────────────

# Security group cho VPC Endpoints (Interface) — cho phép HTTPS từ ECS + worker
resource "aws_security_group" "endpoint" {
  name_prefix = "${var.name_prefix}-endpoint-"
  description = "Cho phep HTTPS (443) tu ECS va worker toi VPC endpoints"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "HTTPS tu ECS tasks"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id, aws_security_group.worker.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-endpoint-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Interface endpoints
resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.ecr.api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private_app[*].id
  security_group_ids  = [aws_security_group.endpoint.id]
  private_dns_enabled = true

  tags = {
    Name = "${var.name_prefix}-vpce-ecr-api"
  }
}

resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private_app[*].id
  security_group_ids  = [aws_security_group.endpoint.id]
  private_dns_enabled = true

  tags = {
    Name = "${var.name_prefix}-vpce-ecr-dkr"
  }
}

resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private_app[*].id
  security_group_ids  = [aws_security_group.endpoint.id]
  private_dns_enabled = true

  tags = {
    Name = "${var.name_prefix}-vpce-secretsmanager"
  }
}

resource "aws_vpc_endpoint" "logs" {
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private_app[*].id
  security_group_ids  = [aws_security_group.endpoint.id]
  private_dns_enabled = true

  tags = {
    Name = "${var.name_prefix}-vpce-logs"
  }
}

resource "aws_vpc_endpoint" "ssm" {
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.ssm"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private_app[*].id
  security_group_ids  = [aws_security_group.endpoint.id]
  private_dns_enabled = true

  tags = {
    Name = "${var.name_prefix}-vpce-ssm"
  }
}

# Gateway endpoint cho S3
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids = [
    aws_route_table.private_app.id,
    aws_route_table.private_data.id,
  ]

  tags = {
    Name = "${var.name_prefix}-vpce-s3"
  }
}

# ─── Security Groups ────────────────────────────────────────────────────────

# ALB security group
resource "aws_security_group" "alb" {
  name_prefix = "${var.name_prefix}-alb-"
  description = "Security group cho Application Load Balancer"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTPS tu Internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP tu Internet (redirect sang 443)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-alb-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ECS tasks security group (api + frontend)
resource "aws_security_group" "ecs" {
  name_prefix = "${var.name_prefix}-ecs-"
  description = "Security group cho ECS Fargate tasks (api + frontend)"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Traffic tu ALB"
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-ecs-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Worker security group (egress only)
resource "aws_security_group" "worker" {
  name_prefix = "${var.name_prefix}-worker-"
  description = "Security group cho ECS worker tasks (egress only)"
  vpc_id      = aws_vpc.this.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-worker-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# RDS (PostgreSQL) security group
resource "aws_security_group" "db" {
  name_prefix = "${var.name_prefix}-db-"
  description = "Security group cho RDS PostgreSQL"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "PostgreSQL tu ECS tasks"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id, aws_security_group.worker.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-db-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ElastiCache (Redis/Valkey) security group
resource "aws_security_group" "redis" {
  name_prefix = "${var.name_prefix}-redis-"
  description = "Security group cho ElastiCache Redis/Valkey"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Redis tu ECS tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id, aws_security_group.worker.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-redis-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ─── Data source ─────────────────────────────────────────────────────────────

data "aws_region" "current" {}
