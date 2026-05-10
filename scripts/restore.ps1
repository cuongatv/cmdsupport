#Requires -Version 5.1
<#
.SYNOPSIS
    Khôi phục Postgres DB và MinIO bucket cho CMD Support từ bản backup.
.PARAMETER BackupDir
    Đường dẫn thư mục backup (chứa cmd_support.sql và minio-arkon-files/).
.EXAMPLE
    .\scripts\restore.ps1 -BackupDir .\backups\20250507_143000
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDir
)

$ErrorActionPreference = "Stop"

# Resolve đường dẫn tuyệt đối
$BackupDir = (Resolve-Path $BackupDir).Path

Write-Host "=== CMD Support Restore ===" -ForegroundColor Cyan
Write-Host "Backup: $BackupDir"
Write-Host ""

# --- Pre-check ---
$sqlFile = Join-Path $BackupDir "cmd_support.sql"
$minioDir = Join-Path $BackupDir "minio-arkon-files"

if (!(Test-Path $sqlFile)) {
    Write-Host "LOI: Khong tim thay $sqlFile" -ForegroundColor Red
    exit 1
}
if (!(Test-Path $minioDir)) {
    Write-Host "LOI: Khong tim thay $minioDir" -ForegroundColor Red
    exit 1
}

Write-Host "Tim thay SQL dump va MinIO backup." -ForegroundColor Green
Write-Host ""

# --- Confirm ---
$confirm = Read-Host "Khoi phuc se XOA DB cmd_support hien tai. Tiep tuc? (y/N)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "Huy bo." -ForegroundColor Yellow
    exit 0
}

Write-Host ""

# --- 1. Stop services ---
Write-Host "[1/5] Dung api/worker/worker_skills..." -ForegroundColor Yellow
docker compose stop api worker worker_skills 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "CANH BAO: Khong the dung services (co the chua chay)." -ForegroundColor Yellow
}

# --- 2. Drop + Recreate DB ---
Write-Host "[2/5] Drop + recreate DB cmd_support..." -ForegroundColor Yellow
docker exec cmd_postgres psql -U arkon -d postgres -c "DROP DATABASE IF EXISTS cmd_support;" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "LOI: Khong the drop DB!" -ForegroundColor Red
    exit 1
}

docker exec cmd_postgres psql -U arkon -d postgres -c "CREATE DATABASE cmd_support OWNER arkon;" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "LOI: Khong the tao lai DB!" -ForegroundColor Red
    exit 1
}
Write-Host "  -> DB da duoc tao lai." -ForegroundColor Green

# --- 3. Restore SQL ---
Write-Host "[3/5] Restore SQL dump..." -ForegroundColor Yellow
Get-Content $sqlFile -Raw | docker exec -i cmd_postgres psql -U arkon -d cmd_support 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "CANH BAO: Restore SQL co loi (co the do warning, kiem tra output)." -ForegroundColor Yellow
}
Write-Host "  -> SQL dump da duoc restore." -ForegroundColor Green

# --- 4. Restore MinIO ---
Write-Host "[4/5] Restore MinIO (arkon-files)..." -ForegroundColor Yellow

# Copy backup vào container
docker exec cmd_minio sh -c "rm -rf /tmp/restore_minio" 2>$null
docker cp $minioDir "cmd_minio:/tmp/restore_minio" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "LOI: Khong the copy MinIO backup vao container!" -ForegroundColor Red
    exit 1
}

# Mirror vào bucket
docker exec cmd_minio sh -c "mc alias set local http://localhost:9000 minioadmin minioadmin123 >/dev/null 2>&1 && mc mirror --overwrite --remove /tmp/restore_minio local/arkon-files" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "LOI: Khong the restore MinIO!" -ForegroundColor Red
    exit 1
}

# Cleanup
docker exec cmd_minio sh -c "rm -rf /tmp/restore_minio" 2>$null
Write-Host "  -> MinIO da duoc restore." -ForegroundColor Green

# --- 5. Start services ---
Write-Host "[5/5] Khoi dong lai api/worker/worker_skills..." -ForegroundColor Yellow
docker compose start api worker worker_skills 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "LOI: Khong the khoi dong services!" -ForegroundColor Red
    exit 1
}

# Đợi API healthy
Write-Host "  Doi API healthy..." -ForegroundColor Yellow
$maxWait = 60
$waited = 0
while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 3
    $waited += 3
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:5055/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($resp.StatusCode -eq 200) {
            Write-Host "  -> API healthy!" -ForegroundColor Green
            break
        }
    } catch {}
}
if ($waited -ge $maxWait) {
    Write-Host "CANH BAO: API chua healthy sau ${maxWait}s. Kiem tra logs." -ForegroundColor Yellow
}

# --- Summary ---
Write-Host ""
Write-Host "=== Restore hoan tat ===" -ForegroundColor Cyan
Write-Host "  DB cmd_support: da khoi phuc tu $sqlFile"
Write-Host "  MinIO arkon-files: da khoi phuc tu $minioDir"
Write-Host ""

exit 0
