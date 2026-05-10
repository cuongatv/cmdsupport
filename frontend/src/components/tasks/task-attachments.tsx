"use client";

import React from "react";
import { ApiError } from "@/lib/api";
import {
  deleteTaskAttachment,
  downloadTaskAttachment,
  listTaskAttachments,
  uploadTaskAttachment,
} from "@/lib/task-api";
import type { TaskAttachment } from "@/lib/task-types";
import { formatTaskDateTime } from "@/lib/task-types";
import { Button } from "@/components/ui/button";

const MAX_ATTACHMENT_BYTES = 26_214_400; // 25 MB
const MAX_ATTACHMENTS_PER_TASK = 10;
const DENIED_EXTENSIONS = new Set([
  ".exe",
  ".bat",
  ".ps1",
  ".sh",
  ".scr",
  ".com",
]);

function getExtension(filename: string): string {
  const idx = filename.lastIndexOf(".");
  if (idx < 0) return "";
  return filename.slice(idx).toLowerCase();
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 413) {
      return "Tệp vượt quá kích thước cho phép (25 MB)";
    }
    if (err.status === 400 && /extension/i.test(err.message)) {
      return "loại tệp không được phép";
    }
    if (err.status === 400 && /count/i.test(err.message)) {
      return "Đã đạt giới hạn 10 tệp đính kèm cho công việc này";
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

export type TaskAttachmentsProps = {
  taskId: string;
  canDelete: boolean;
};

export function TaskAttachments({ taskId, canDelete }: TaskAttachmentsProps) {
  const [attachments, setAttachments] = React.useState<TaskAttachment[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [uploading, setUploading] = React.useState(false);
  const [downloadingId, setDownloadingId] = React.useState<string | null>(null);
  const [deletingId, setDeletingId] = React.useState<string | null>(null);
  const [error, setError] = React.useState("");
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  const loadAttachments = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await listTaskAttachments(taskId);
      setAttachments(data);
      setError("");
    } catch (err) {
      setAttachments([]);
      setError(getErrorMessage(err, "Không tải được danh sách tệp đính kèm"));
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  React.useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadAttachments();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadAttachments]);

  const handleFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    // Reset the input so the same file can be re-selected after errors.
    event.target.value = "";
    if (!file) return;

    setError("");

    const extension = getExtension(file.name);
    if (DENIED_EXTENSIONS.has(extension)) {
      setError("loại tệp không được phép");
      return;
    }
    if (file.size > MAX_ATTACHMENT_BYTES) {
      setError("Tệp vượt quá kích thước cho phép (25 MB)");
      return;
    }
    if (attachments.length >= MAX_ATTACHMENTS_PER_TASK) {
      setError("Đã đạt giới hạn 10 tệp đính kèm cho công việc này");
      return;
    }

    setUploading(true);
    try {
      await uploadTaskAttachment(taskId, file);
      await loadAttachments();
    } catch (err) {
      setError(getErrorMessage(err, "Tải tệp lên thất bại"));
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (attachment: TaskAttachment) => {
    setError("");
    setDownloadingId(attachment.id);
    try {
      const dto = await downloadTaskAttachment(taskId, attachment.id);
      window.open(dto.presigned_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(getErrorMessage(err, "Không lấy được liên kết tải tệp"));
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDelete = async (attachment: TaskAttachment) => {
    if (
      !confirm(
        `Xóa tệp "${attachment.filename}"? Hành động không thể hoàn tác.`
      )
    ) {
      return;
    }
    setError("");
    setDeletingId(attachment.id);
    try {
      await deleteTaskAttachment(taskId, attachment.id);
      await loadAttachments();
    } catch (err) {
      setError(getErrorMessage(err, "Xóa tệp đính kèm thất bại"));
    } finally {
      setDeletingId(null);
    }
  };

  const reachedLimit = attachments.length >= MAX_ATTACHMENTS_PER_TASK;
  const uploadDisabled = uploading || reachedLimit;

  return (
    <div className="flex flex-col gap-3" data-testid="task-attachments">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          {attachments.length} / {MAX_ATTACHMENTS_PER_TASK} tệp · tối đa 25 MB
          mỗi tệp
        </span>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            data-testid="task-attachment-input"
            onChange={handleFileChange}
            disabled={uploadDisabled}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={uploadDisabled}
            onClick={() => fileInputRef.current?.click()}
            data-testid="task-attachment-upload-btn"
          >
            <span className="material-symbols-outlined text-sm">upload</span>
            {uploading ? "Đang tải lên…" : "Tải tệp lên"}
          </Button>
        </div>
      </div>

      {reachedLimit && (
        <p
          className="text-xs text-muted-foreground italic"
          data-testid="task-attachment-limit-note"
        >
          Đã đạt giới hạn 10 tệp đính kèm cho công việc này.
        </p>
      )}

      {error && (
        <p
          className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
          role="alert"
          data-testid="task-attachment-error"
        >
          {error}
        </p>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-6">
          <span className="material-symbols-outlined text-2xl text-muted-foreground animate-spin">
            progress_activity
          </span>
        </div>
      ) : attachments.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-6">
          Chưa có tệp đính kèm nào.
        </p>
      ) : (
        <ul
          className="flex flex-col gap-1.5"
          data-testid="task-attachment-list"
        >
          {attachments.map((att) => (
            <li
              key={att.id}
              className="flex items-center gap-2.5 rounded-lg border border-border bg-background px-3 py-2"
              data-testid={`task-attachment-${att.id}`}
            >
              <span className="material-symbols-outlined text-lg text-muted-foreground">
                attach_file
              </span>
              <div className="flex flex-col flex-1 min-w-0">
                <span className="truncate text-sm font-medium text-foreground">
                  {att.filename}
                </span>
                <span className="text-[11px] text-muted-foreground tabular-nums">
                  {formatBytes(att.size_bytes)} ·{" "}
                  {formatTaskDateTime(att.created_at)}
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleDownload(att)}
                disabled={downloadingId === att.id}
                data-testid={`task-attachment-download-${att.id}`}
              >
                <span className="material-symbols-outlined text-sm">
                  download
                </span>
                {downloadingId === att.id ? "Đang tải…" : "Tải"}
              </Button>
              {canDelete && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => handleDelete(att)}
                  disabled={deletingId === att.id}
                  data-testid={`task-attachment-delete-${att.id}`}
                  className="text-destructive hover:bg-destructive/10"
                  aria-label="Xóa tệp đính kèm"
                >
                  <span className="material-symbols-outlined text-sm">
                    delete
                  </span>
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
