#Requires -Version 5.1
<#
.SYNOPSIS
    Backup Postgres DB và MinIO bucket cho CMD Support.
.DESCRIPTION
    Tạo bản backup đầy đủ gồm:
      - PostgreSQL dump (cmd_support)
      - MinIO bucket (arkon-files)
    Lưu vào thư mục backups/<timestamp>/
#>

$ErrorActionPreference = "Stop"

# Timestamp
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $PSScriptRoot "..\backups\$ts"

Write-Host "=== CMD Support Backup ===" -ForegroundColor Cyan
Write-Host "Thoi gian: $ts"
Write-Host "Thu muc:   $backupDir"
Write-Host ""

# Tạo thư mục backup
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

# --- 1. Backup Postgres ---
Write-Host "[1/2] Backup PostgreSQL (cmd_support)..." -ForegroundColor Yellow
$sqlFile = Join-Path $backupDir "cmd_support.sql"

docker exec cmd_postgres sh -c "pg_dump -U arkon -d cmd_support" > $sqlFile 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "LOI: Khong the dump PostgreSQL!" -ForegroundColor Red
    exit 1
}

$sqlSize = (Get-Item $sqlFile).Length
Write-Host "  -> SQL dump: $([math]::Round($sqlSize / 1KB, 1)) KB" -ForegroundColor Green

# --- 2. Backup MinIO ---
Write-Host "[2/2] Backup MinIO (arkon-files)..." -ForegroundColor Yellow

# Dùng mc trong container minio để mirror bucket ra /tmp/backup_minio
docker exec cmd_minio sh -c "mc alias set local http://localhost:9000 minioadmin minioadmin123 >/dev/null 2>&1 && rm -rf /tmp/backup_minio && mc mirror --overwrite local/arkon-files /tmp/backup_minio" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "LOI: Khong the backup MinIO!" -ForegroundColor Red
    exit 1
}

# Copy từ container ra host
$minioDir = Join-Path $backupDir "minio-arkon-files"
docker cp "cmd_minio:/tmp/backup_minio" $minioDir 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "LOI: Khong the copy MinIO backup ra host!" -ForegroundColor Red
    exit 1
}

# Đếm file MinIO
$minioFiles = (Get-ChildItem -Path $minioDir -Recurse -File -ErrorAction SilentlyContinue).Count
Write-Host "  -> MinIO objects: $minioFiles file(s)" -ForegroundColor Green

# Cleanup trong container
docker exec cmd_minio sh -c "rm -rf /tmp/backup_minio" 2>$null

# --- Summary ---
Write-Host ""
Write-Host "=== Backup hoan tat ===" -ForegroundColor Cyan
Write-Host "  SQL dump : $sqlFile ($([math]::Round($sqlSize / 1KB, 1)) KB)"
Write-Host "  MinIO    : $minioDir ($minioFiles objects)"
Write-Host "  Thu muc  : $backupDir"
Write-Host ""

exit 0
