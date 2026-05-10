# CMD Support — AWS Infrastructure (Terraform)

Terraform IaC triển khai toàn bộ hạ tầng AWS cho CMD Support tại region **ap-southeast-1** (Singapore).

## Mục lục

1. [Kiến trúc tổng quan](#kiến-trúc-tổng-quan)
2. [Yêu cầu trước khi triển khai](#yêu-cầu-trước-khi-triển-khai)
3. [Bootstrap state backend](#bootstrap-state-backend)
4. [Cách deploy](#cách-deploy)
5. [Push image lần đầu thủ công](#push-image-lần-đầu-thủ-công)
6. [Chạy database migration](#chạy-database-migration)
7. [Verify](#verify)
8. [Tear down](#tear-down)
9. [Chi phí dự kiến](#chi-phí-dự-kiến)
10. [Cấu trúc thư mục](#cấu-trúc-thư-mục)

---

## Kiến trúc tổng quan

```
Internet
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  WAF v2 (Common Rules + Bad Inputs + Rate Limit)     │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────┐
│  ALB (public, 2 AZs)                                 │
│  ├─ cmdsupport.com / www → Frontend TG (port 3000)   │
│  └─ api.cmdsupport.com   → API TG (port 5055)        │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────┐
│  ECS Fargate (private app subnets, 2 AZs)            │
│  ├─ cmd-api          (0.5 vCPU / 1 GB)               │
│  ├─ cmd-worker       (0.5 vCPU / 1 GB)               │
│  ├─ cmd-worker-skills(0.5 vCPU / 1 GB)               │
│  └─ cmd-frontend     (0.5 vCPU / 1 GB)               │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────┐
│  Data Tier (private data subnets, không có Internet)  │
│  ├─ RDS PostgreSQL 16 (pgvector) — 50GB gp3           │
│  ├─ ElastiCache Valkey Serverless                     │
│  └─ S3 Bucket (versioning, SSE-KMS, block public)    │
└──────────────────────────────────────────────────────┘
```

**Domain**: cmdsupport.com | www.cmdsupport.com | api.cmdsupport.com
**VPC**: 10.20.0.0/16 — 2 AZ (ap-southeast-1a, ap-southeast-1b)
**NAT Gateway**: 1 (pilot) — có thể mở rộng 2 cho prod

---

## Yêu cầu trước khi triển khai

| Yêu cầu | Chi tiết |
|----------|----------|
| AWS Account | IAM user/role với quyền `AdministratorAccess` (chỉ để bootstrap) |
| Terraform | >= 1.6 ([tải về](https://developer.hashicorp.com/terraform/downloads)) |
| AWS CLI | v2 ([tải về](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)) |
| Domain | `cmdsupport.com` đã trỏ NS về Route 53 hosted zone |
| GitHub repo | URL repo cho OIDC (vd: `myorg/cmd-support`) |
| Docker | Để build và push image lần đầu |

### Chuẩn bị Route 53 Hosted Zone

Nếu chưa có hosted zone:

```bash
aws route53 create-hosted-zone --name cmdsupport.com --caller-reference "$(date +%s)"
```

Lấy Name Servers từ output và cập nhật NS records tại domain registrar.

---

## Bootstrap state backend

Tạo S3 bucket + DynamoDB lock table cho remote state (**chạy 1 lần duy nhất, thủ công**):

```bash
# Tạo S3 bucket
aws s3api create-bucket \
  --bucket cmd-support-terraform-state \
  --region ap-southeast-1 \
  --create-bucket-configuration LocationConstraint=ap-southeast-1

# Bật versioning
aws s3api put-bucket-versioning \
  --bucket cmd-support-terraform-state \
  --versioning-configuration Status=Enabled

# Bật encryption
aws s3api put-bucket-encryption \
  --bucket cmd-support-terraform-state \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'

# Block public access
aws s3api put-public-access-block \
  --bucket cmd-support-terraform-state \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Tạo DynamoDB table cho state locking
aws dynamodb create-table \
  --table-name cmd-support-terraform-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-southeast-1
```

Sau đó copy `backend.tf.example` thành `backend.tf` và bỏ comment.

---

## Cách deploy

### 1. Chuẩn bị tfvars

```bash
cp terraform.tfvars.example terraform.tfvars
# Sửa terraform.tfvars theo môi trường thực tế
```

### 2. Khởi tạo và triển khai

```bash
# Khởi tạo providers + modules
terraform init

# Xem trước thay đổi
terraform plan -var-file=terraform.tfvars

# Triển khai
terraform apply -var-file=terraform.tfvars
```

### 3. Lần đầu — image chưa có trong ECR

Lần deploy đầu tiên, ECS service sẽ fail vì chưa có image trong ECR.
Sau khi `terraform apply` thành công (tạo xong ECR repos), push image theo hướng dẫn bên dưới rồi chạy lại:

```bash
terraform apply -var-file=terraform.tfvars \
  -var image_tag_api=<commit-sha> \
  -var image_tag_frontend=<commit-sha>
```

Hoặc để GitHub Actions CI/CD tự deploy sau.

---

## Push image lần đầu thủ công

```bash
# Lấy Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="ap-southeast-1"

# Login ECR
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

# === Backend ===
docker build -t cmd-support-backend:latest .
docker tag cmd-support-backend:latest \
  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/cmd-support-backend:bootstrap
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/cmd-support-backend:bootstrap

# === Frontend ===
docker build -t cmd-support-frontend:latest ./frontend
docker tag cmd-support-frontend:latest \
  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/cmd-support-frontend:bootstrap
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/cmd-support-frontend:bootstrap
```

Sau khi push xong, ECS service sẽ tự pull image và khởi động task.

---

## Chạy database migration

Chạy Alembic migration lần đầu qua ECS run-task:

```bash
CLUSTER="cmd-support-pilot"
TASK_DEF="cmd-pilot-api"
SUBNETS="<private-app-subnet-1>,<private-app-subnet-2>"  # Lấy từ terraform output
SG="<ecs-security-group-id>"  # Lấy từ terraform output

aws ecs run-task \
  --cluster $CLUSTER \
  --task-definition $TASK_DEF \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG]}" \
  --overrides '{
    "containerOverrides": [{
      "name": "cmd-api",
      "command": ["sh", "-c", "alembic upgrade head"]
    }]
  }' \
  --region ap-southeast-1
```

Theo dõi logs tại CloudWatch Log Group `/ecs/cmd-api`.

---

## Verify

```bash
# Kiểm tra DNS
nslookup api.cmdsupport.com
nslookup cmdsupport.com

# Kiểm tra API health
curl -s https://api.cmdsupport.com/health
# Expected: HTTP 200

# Kiểm tra Frontend
curl -s -o /dev/null -w "%{http_code}" https://cmdsupport.com/login
# Expected: 200
```

---

## Tear down

```bash
# LƯU Ý: Nếu db_deletion_protection = true, phải set false trước
terraform apply -var db_deletion_protection=false

# Destroy toàn bộ
terraform destroy -var-file=terraform.tfvars
```

**Cảnh báo**: `terraform destroy` sẽ xóa toàn bộ tài nguyên bao gồm database, S3 bucket, và secrets. Đảm bảo đã backup dữ liệu trước khi destroy.

---

## Chi phí dự kiến

Bảng ước tính chi phí hàng tháng cho môi trường **pilot** (ap-southeast-1, tháng 5/2025):

| Dịch vụ | Spec | Chi phí/tháng (USD) |
|---------|------|---------------------|
| **ECS Fargate** | 4 tasks x 0.5 vCPU x 1 GB | ~$58 |
| **RDS PostgreSQL** | db.t4g.medium, Single-AZ, 50GB gp3 | ~$52 |
| **ElastiCache Valkey Serverless** | 1 GB data, 1000 ECPU/s | ~$10-20 |
| **NAT Gateway** | 1 GW + data processing | ~$35 |
| **ALB** | 1 ALB + LCU | ~$22 |
| **S3** | < 10 GB | ~$1 |
| **VPC Endpoints** | 5 Interface + 1 Gateway | ~$55 |
| **Route 53** | 1 hosted zone + queries | ~$1 |
| **ACM** | Certificate (miễn phí) | $0 |
| **WAF v2** | 1 Web ACL + 3 rules | ~$11 |
| **CloudWatch Logs** | Ingestion + storage | ~$5 |
| **ECR** | Image storage | ~$1 |
| **Secrets Manager** | 2 secrets | ~$1 |
| | **Tổng ước tính** | **~$250-270/tháng** |

> Chi phí thực tế phụ thuộc vào traffic, data transfer, và storage usage.
> Để tiết kiệm thêm: cân nhắc giảm số VPC Interface Endpoints (dùng NAT GW thay thế cho một số endpoint).

---

## Cấu trúc thư mục

```
infra/aws/
├── README.md                    # File này
├── versions.tf                  # Phiên bản Terraform + providers
├── providers.tf                 # Provider config (ap-southeast-1 + us-east-1 alias)
├── variables.tf                 # Tất cả input variables
├── locals.tf                    # Tags chuẩn, naming convention
├── main.tf                      # Gọi các modules
├── outputs.tf                   # Output values
├── terraform.tfvars.example     # Mẫu giá trị cấu hình
├── backend.tf.example           # Cấu hình S3 remote state (mẫu)
└── modules/
    ├── network/                 # VPC, Subnets, NAT, IGW, Route Tables, VPC Endpoints, Security Groups
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── data/                    # RDS PostgreSQL 16, ElastiCache Valkey/Redis, S3
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── secrets/                 # Secrets Manager + SSM Parameter Store
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── compute/                 # ECR, ECS Cluster, Task Definitions, Services, ALB
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── edge/                    # ACM Certificate, Route53 DNS Records
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── waf/                     # WAFv2 Web ACL + ALB association
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    └── iam_github_oidc/         # GitHub Actions OIDC Provider + IAM Role
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

---

## Variables reference

| Variable | Default | Mô tả |
|----------|---------|-------|
| `aws_region` | `ap-southeast-1` | AWS region |
| `environment` | `pilot` | Môi trường (pilot/staging/prod) |
| `domain_name` | `cmdsupport.com` | Domain chính |
| `vpc_cidr` | `10.20.0.0/16` | CIDR VPC |
| `az_count` | `2` | Số AZs |
| `db_instance_class` | `db.t4g.medium` | RDS instance type |
| `db_multi_az` | `false` | Multi-AZ cho RDS |
| `db_deletion_protection` | `true` | Bảo vệ xóa RDS |
| `use_serverless_redis` | `true` | Dùng Valkey Serverless |
| `api_desired_count` | `1` | Số task API |
| `enable_cloudfront` | `false` | Bật CloudFront CDN |
| `github_repo` | `ORG/cmd-support` | GitHub repo cho OIDC |
| `image_tag_api` | `bootstrap` | Tag image backend |
| `image_tag_frontend` | `bootstrap` | Tag image frontend |
| `log_retention_days` | `30` | Ngày giữ CloudWatch logs |

Xem đầy đủ tại `variables.tf`.
