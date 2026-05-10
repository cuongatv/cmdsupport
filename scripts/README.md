# Scripts Backup / Restore — CMD Support

## Yêu cầu

- PowerShell 5.1+
- Docker Desktop đang chạy, các container `cmd_postgres` và `cmd_minio` đang hoạt động.

## Backup

```powershell
.\scripts\backup.ps1
```

Tạo bản backup tại `backups/<yyyyMMdd_HHmmss>/` gồm:
- `cmd_support.sql` — dump toàn bộ DB PostgreSQL
- `minio-arkon-files/` — toàn bộ file trong bucket MinIO

## Restore

```powershell
.\scripts\restore.ps1 -BackupDir .\backups\20250507_143000
```

Script sẽ:
1. Kiểm tra folder backup hợp lệ
2. Hỏi xác nhận (vì sẽ xoá DB hiện tại)
3. Dừng api/worker/worker_skills
4. Drop + recreate DB, restore SQL dump
5. Restore MinIO bucket
6. Khởi động lại services, kiểm tra health

**Lưu ý:** Restore sẽ XOÁ toàn bộ dữ liệu hiện tại và thay bằng bản backup.
