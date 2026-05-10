# =============================================================================
# Compute module — ECR, ECS Cluster, Task Definitions, Services, ALB
# =============================================================================

# ─── ECR Repositories ───────────────────────────────────────────────────────

resource "aws_ecr_repository" "backend" {
  name                 = "cmd-support-backend"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.environment != "prod"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "cmd-support-backend"
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "cmd-support-frontend"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.environment != "prod"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "cmd-support-frontend"
  }
}

# Lifecycle policy — giữ 30 image cuối
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Giu 30 image gan nhat"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 30
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

resource "aws_ecr_lifecycle_policy" "frontend" {
  repository = aws_ecr_repository.frontend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Giu 30 image gan nhat"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 30
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ─── CloudWatch Log Groups ──────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/cmd-api"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.name_prefix}-log-api"
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/cmd-worker"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.name_prefix}-log-worker"
  }
}

resource "aws_cloudwatch_log_group" "worker_skills" {
  name              = "/ecs/cmd-worker-skills"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.name_prefix}-log-worker-skills"
  }
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/cmd-frontend"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.name_prefix}-log-frontend"
  }
}

# ─── IAM Roles ───────────────────────────────────────────────────────────────

# ECS Task Execution Role (pull image, read secrets, write logs)
resource "aws_iam_role" "ecs_execution" {
  name = "${var.name_prefix}-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.name_prefix}-ecs-execution"
  }
}

resource "aws_iam_role_policy_attachment" "ecs_execution_base" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${var.name_prefix}-ecs-execution-secrets"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          var.secret_key_arn,
          var.db_password_arn,
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameters",
          "ssm:GetParameter"
        ]
        Resource = [
          var.cors_origins_arn,
          var.next_public_api_url_arn,
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "${aws_cloudwatch_log_group.api.arn}:*",
          "${aws_cloudwatch_log_group.worker.arn}:*",
          "${aws_cloudwatch_log_group.worker_skills.arn}:*",
          "${aws_cloudwatch_log_group.frontend.arn}:*",
        ]
      }
    ]
  })
}

# ECS Task Role — cho api + worker (S3 access)
resource "aws_iam_role" "ecs_task_app" {
  name = "${var.name_prefix}-ecs-task-app"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.name_prefix}-ecs-task-app"
  }
}

resource "aws_iam_role_policy" "ecs_task_app_s3" {
  name = "${var.name_prefix}-ecs-task-s3"
  role = aws_iam_role.ecs_task_app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${var.s3_bucket_arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = var.s3_bucket_arn
      }
    ]
  })
}

# ECS Task Role — cho frontend (quyền tối thiểu, chỉ logs)
resource "aws_iam_role" "ecs_task_frontend" {
  name = "${var.name_prefix}-ecs-task-frontend"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.name_prefix}-ecs-task-frontend"
  }
}

# ─── ECS Cluster ─────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "this" {
  name = "cmd-support-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "cmd-support-${var.environment}"
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name = aws_ecs_cluster.this.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

# ─── Task Definitions ───────────────────────────────────────────────────────

locals {
  backend_image  = "${aws_ecr_repository.backend.repository_url}:${var.image_tag_api}"
  frontend_image = "${aws_ecr_repository.frontend.repository_url}:${var.image_tag_frontend}"
}

# cmd-api task definition
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name_prefix}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_app.arn

  container_definitions = jsonencode([
    {
      name      = "cmd-api"
      image     = local.backend_image
      essential = true
      command   = ["sh", "-c", "alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port 5055"]

      portMappings = [
        {
          containerPort = 5055
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "STORAGE_BACKEND", value = "s3" },
        { name = "S3_REGION", value = var.aws_region },
        { name = "S3_BUCKET", value = var.s3_bucket_name },
        { name = "CORS_ORIGINS", value = "https://${var.domain_name},https://www.${var.domain_name}" },
        { name = "NEXT_PUBLIC_API_URL", value = "https://api.${var.domain_name}" },
        { name = "REDIS_HOST", value = var.redis_endpoint },
        { name = "REDIS_PORT", value = tostring(var.redis_port) },
        { name = "DATABASE_URL", value = "postgresql+asyncpg://cmd_support_admin:PLACEHOLDER@${var.rds_address}:${var.rds_port}/${var.rds_db_name}" },
      ]

      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = var.secret_key_arn
        },
        {
          name      = "DB_PASSWORD"
          valueFrom = var.db_password_arn
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:5055/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${var.name_prefix}-api-task"
  }
}

# cmd-worker task definition
resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name_prefix}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_app.arn

  container_definitions = jsonencode([
    {
      name      = "cmd-worker"
      image     = local.backend_image
      essential = true
      command   = ["python", "-m", "arq", "app.worker.WorkerSettings"]

      environment = [
        { name = "STORAGE_BACKEND", value = "s3" },
        { name = "S3_REGION", value = var.aws_region },
        { name = "S3_BUCKET", value = var.s3_bucket_name },
        { name = "REDIS_HOST", value = var.redis_endpoint },
        { name = "REDIS_PORT", value = tostring(var.redis_port) },
        { name = "DATABASE_URL", value = "postgresql+asyncpg://cmd_support_admin:PLACEHOLDER@${var.rds_address}:${var.rds_port}/${var.rds_db_name}" },
      ]

      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = var.secret_key_arn
        },
        {
          name      = "DB_PASSWORD"
          valueFrom = var.db_password_arn
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = {
    Name = "${var.name_prefix}-worker-task"
  }
}

# cmd-worker-skills task definition
resource "aws_ecs_task_definition" "worker_skills" {
  family                   = "${var.name_prefix}-worker-skills"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_app.arn

  container_definitions = jsonencode([
    {
      name      = "cmd-worker-skills"
      image     = local.backend_image
      essential = true
      command   = ["python", "-m", "arq", "app.worker.SkillWorkerSettings"]

      environment = [
        { name = "STORAGE_BACKEND", value = "s3" },
        { name = "S3_REGION", value = var.aws_region },
        { name = "S3_BUCKET", value = var.s3_bucket_name },
        { name = "REDIS_HOST", value = var.redis_endpoint },
        { name = "REDIS_PORT", value = tostring(var.redis_port) },
        { name = "DATABASE_URL", value = "postgresql+asyncpg://cmd_support_admin:PLACEHOLDER@${var.rds_address}:${var.rds_port}/${var.rds_db_name}" },
      ]

      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = var.secret_key_arn
        },
        {
          name      = "DB_PASSWORD"
          valueFrom = var.db_password_arn
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker_skills.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = {
    Name = "${var.name_prefix}-worker-skills-task"
  }
}

# cmd-frontend task definition
resource "aws_ecs_task_definition" "frontend" {
  family                   = "${var.name_prefix}-frontend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.frontend_cpu
  memory                   = var.frontend_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_frontend.arn

  container_definitions = jsonencode([
    {
      name      = "cmd-frontend"
      image     = local.frontend_image
      essential = true

      portMappings = [
        {
          containerPort = 3000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "NEXT_PUBLIC_API_URL", value = "https://api.${var.domain_name}" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.frontend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:3000/ || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${var.name_prefix}-frontend-task"
  }
}

# ─── ALB ─────────────────────────────────────────────────────────────────────

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.environment == "prod"

  tags = {
    Name = "${var.name_prefix}-alb"
  }
}

# Target Groups
resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api-tg"
  port        = 5055
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    path                = "/health"
    matcher             = "200"
  }

  tags = {
    Name = "${var.name_prefix}-api-tg"
  }
}

resource "aws_lb_target_group" "frontend" {
  name        = "${var.name_prefix}-fe-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    path                = "/"
    matcher             = "200"
  }

  tags = {
    Name = "${var.name_prefix}-frontend-tg"
  }
}

# Listener 80 → redirect 443
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }

  tags = {
    Name = "${var.name_prefix}-http-listener"
  }
}

# Listener 443 — default forward về frontend
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  tags = {
    Name = "${var.name_prefix}-https-listener"
  }
}

# Listener rule: api.cmdsupport.com → api target group
resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 100

  condition {
    host_header {
      values = ["api.${var.domain_name}"]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  tags = {
    Name = "${var.name_prefix}-api-rule"
  }
}

# Listener rule: cmdsupport.com + www.cmdsupport.com → frontend target group
resource "aws_lb_listener_rule" "frontend" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 200

  condition {
    host_header {
      values = [var.domain_name, "www.${var.domain_name}"]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  tags = {
    Name = "${var.name_prefix}-frontend-rule"
  }
}

# ─── ECS Services ───────────────────────────────────────────────────────────

resource "aws_ecs_service" "api" {
  name            = "${var.name_prefix}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_app_subnet_ids
    security_groups = [var.ecs_security_group_id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "cmd-api"
    container_port   = 5055
  }

  tags = {
    Name = "${var.name_prefix}-api-service"
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.https]
}

resource "aws_ecs_service" "worker" {
  name            = "${var.name_prefix}-worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_app_subnet_ids
    security_groups = [var.worker_security_group_id]
  }

  tags = {
    Name = "${var.name_prefix}-worker-service"
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

resource "aws_ecs_service" "worker_skills" {
  name            = "${var.name_prefix}-worker-skills"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker_skills.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_app_subnet_ids
    security_groups = [var.worker_security_group_id]
  }

  tags = {
    Name = "${var.name_prefix}-worker-skills-service"
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

resource "aws_ecs_service" "frontend" {
  name            = "${var.name_prefix}-frontend"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.frontend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_app_subnet_ids
    security_groups = [var.ecs_security_group_id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "cmd-frontend"
    container_port   = 3000
  }

  tags = {
    Name = "${var.name_prefix}-frontend-service"
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.https]
}
