"use client";

import React from "react";
import { ApiError } from "@/lib/api";
import {
  createTaskComment,
  deleteTaskComment,
  listTaskComments,
  updateTaskComment,
} from "@/lib/task-api";
import type { EligibleAssignee, TaskComment } from "@/lib/task-types";
import { formatTaskDateTime } from "@/lib/task-types";
import { Button } from "@/components/ui/button";

const MENTION_TAG_RE = /<mention id="([^"]+)">([^<]+)<\/mention>/g;
const MAX_COMMENT_BYTES = 65_536;

const TEXTAREA_CLASS =
  "flex field-sizing-content min-h-20 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-base transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 md:text-sm dark:bg-input/30 dark:disabled:bg-input/80";

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function bodyByteLength(value: string): number {
  return new TextEncoder().encode(value).length;
}

function renderCommentBody(body: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let lastIdx = 0;
  let key = 0;
  // Local regex instance to keep state isolated per render.
  const re = new RegExp(MENTION_TAG_RE.source, "g");
  let match: RegExpExecArray | null = re.exec(body);
  while (match !== null) {
    if (match.index > lastIdx) {
      out.push(
        <span key={`t${key++}`}>{body.slice(lastIdx, match.index)}</span>
      );
    }
    out.push(
      <span
        key={`m${key++}`}
        className="inline-flex items-center rounded bg-primary/10 text-primary px-1.5 py-0.5 text-xs font-medium mx-0.5"
      >
        {match[2]}
      </span>
    );
    lastIdx = match.index + match[0].length;
    match = re.exec(body);
  }
  if (lastIdx < body.length) {
    out.push(<span key={`t${key++}`}>{body.slice(lastIdx)}</span>);
  }
  return out;
}

export type TaskCommentsProps = {
  taskId: string;
  currentUserId: string | null;
  eligibleAssignees: EligibleAssignee[];
};

export function TaskComments({
  taskId,
  currentUserId,
  eligibleAssignees,
}: TaskCommentsProps) {
  const [comments, setComments] = React.useState<TaskComment[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [newBody, setNewBody] = React.useState("");
  const [posting, setPosting] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editingBody, setEditingBody] = React.useState("");
  const [savingEdit, setSavingEdit] = React.useState(false);
  const [deletingId, setDeletingId] = React.useState<string | null>(null);
  const [mentionPickerOpen, setMentionPickerOpen] = React.useState(false);
  const newBodyRef = React.useRef<HTMLTextAreaElement | null>(null);

  const employeeMap = Object.fromEntries(
    eligibleAssignees.map((e) => [e.id, e])
  );

  const loadComments = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await listTaskComments(taskId);
      setComments(data);
      setError("");
    } catch (err) {
      setComments([]);
      setError(getErrorMessage(err, "Không tải được bình luận"));
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  React.useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadComments();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadComments]);

  const insertMention = (assignee: EligibleAssignee) => {
    const tag = `<mention id="${assignee.id}">@${assignee.name}</mention>`;
    const ta = newBodyRef.current;
    if (!ta) {
      setNewBody((b) => (b.length > 0 ? `${b} ${tag} ` : `${tag} `));
      setMentionPickerOpen(false);
      return;
    }
    const start = ta.selectionStart ?? newBody.length;
    const end = ta.selectionEnd ?? newBody.length;
    const before = newBody.slice(0, start);
    const after = newBody.slice(end);
    const insertion = `${tag} `;
    const next = before + insertion + after;
    setNewBody(next);
    setMentionPickerOpen(false);
    window.setTimeout(() => {
      const node = newBodyRef.current;
      if (!node) return;
      const cursor = start + insertion.length;
      node.focus();
      node.selectionStart = cursor;
      node.selectionEnd = cursor;
    }, 0);
  };

  const handlePost = async () => {
    const trimmed = newBody.trim();
    if (!trimmed) {
      setError("Nội dung bình luận không được trống");
      return;
    }
    if (bodyByteLength(trimmed) > MAX_COMMENT_BYTES) {
      setError("Nội dung bình luận quá dài (tối đa 64 KB)");
      return;
    }
    setError("");
    setPosting(true);
    try {
      await createTaskComment(taskId, { body: trimmed });
      setNewBody("");
      await loadComments();
    } catch (err) {
      setError(getErrorMessage(err, "Đăng bình luận thất bại"));
    } finally {
      setPosting(false);
    }
  };

  const startEdit = (c: TaskComment) => {
    setEditingId(c.id);
    setEditingBody(c.body);
    setError("");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingBody("");
  };

  const saveEdit = async (commentId: string) => {
    const trimmed = editingBody.trim();
    if (!trimmed) {
      setError("Nội dung bình luận không được trống");
      return;
    }
    if (bodyByteLength(trimmed) > MAX_COMMENT_BYTES) {
      setError("Nội dung bình luận quá dài (tối đa 64 KB)");
      return;
    }
    setSavingEdit(true);
    try {
      await updateTaskComment(taskId, commentId, { body: trimmed });
      setEditingId(null);
      setEditingBody("");
      await loadComments();
    } catch (err) {
      setError(getErrorMessage(err, "Cập nhật bình luận thất bại"));
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async (commentId: string) => {
    if (!confirm("Xóa bình luận này? Hành động không thể hoàn tác.")) return;
    setError("");
    setDeletingId(commentId);
    try {
      await deleteTaskComment(taskId, commentId);
      await loadComments();
    } catch (err) {
      setError(getErrorMessage(err, "Xóa bình luận thất bại"));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-3" data-testid="task-comments">
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-background p-3">
        <textarea
          ref={newBodyRef}
          data-testid="task-comment-input"
          value={newBody}
          onChange={(e) => setNewBody(e.target.value)}
          placeholder="Viết bình luận… Bấm Đề cập để nhắc đến đồng đội."
          className={TEXTAREA_CLASS}
        />
        <div className="flex items-center justify-between gap-2">
          <div className="relative">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setMentionPickerOpen((o) => !o)}
              data-testid="task-comment-mention-btn"
            >
              <span className="material-symbols-outlined text-sm">
                alternate_email
              </span>
              Đề cập
            </Button>
            {mentionPickerOpen && (
              <div
                className="absolute z-20 left-0 top-full mt-1 w-64 max-h-64 overflow-y-auto rounded-lg border border-border bg-popover p-1 shadow-lg"
                data-testid="task-comment-mention-list"
              >
                {eligibleAssignees.length === 0 ? (
                  <p className="px-2 py-1.5 text-xs text-muted-foreground">
                    Chưa có người để đề cập
                  </p>
                ) : (
                  eligibleAssignees.map((emp) => (
                    <button
                      key={emp.id}
                      type="button"
                      onClick={() => insertMention(emp)}
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted/40"
                      data-testid={`task-comment-mention-${emp.id}`}
                    >
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-bold text-primary">
                        {emp.name.charAt(0).toUpperCase()}
                      </span>
                      <span className="flex flex-col min-w-0">
                        <span className="text-sm truncate">{emp.name}</span>
                        <span className="text-[11px] text-muted-foreground truncate">
                          {emp.email}
                        </span>
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
          <Button
            onClick={handlePost}
            disabled={posting || newBody.trim().length === 0}
            data-testid="task-comment-submit-btn"
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            {posting ? (
              <span className="flex items-center gap-1.5">
                <span className="material-symbols-outlined animate-spin text-sm">
                  progress_activity
                </span>
                Đang gửi…
              </span>
            ) : (
              "Gửi bình luận"
            )}
          </Button>
        </div>
      </div>

      {error && (
        <p
          className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
          role="alert"
          data-testid="task-comment-error"
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
      ) : comments.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-6">
          Chưa có bình luận nào.
        </p>
      ) : (
        <ul
          className="flex flex-col gap-2"
          data-testid="task-comment-list"
        >
          {comments.map((c) => {
            const author = c.author_id ? employeeMap[c.author_id] : null;
            const isOwn =
              currentUserId !== null && c.author_id === currentUserId;
            const isEditing = editingId === c.id;
            return (
              <li
                key={c.id}
                className="flex flex-col gap-1.5 rounded-lg border border-border bg-background px-3 py-2"
                data-testid={`task-comment-${c.id}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0 flex-wrap">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-bold text-primary">
                      {(author?.name ?? "?").charAt(0).toUpperCase()}
                    </span>
                    <span className="text-sm font-medium truncate">
                      {author?.name ?? "Người dùng"}
                    </span>
                    <span className="text-[11px] text-muted-foreground tabular-nums">
                      {formatTaskDateTime(c.created_at)}
                    </span>
                    {c.is_edited && (
                      <span className="text-[11px] text-muted-foreground italic">
                        (đã chỉnh sửa)
                      </span>
                    )}
                  </div>
                  {isOwn && !isEditing && (
                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => startEdit(c)}
                        data-testid={`task-comment-edit-${c.id}`}
                        aria-label="Chỉnh sửa bình luận"
                      >
                        <span className="material-symbols-outlined text-sm">
                          edit
                        </span>
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => handleDelete(c.id)}
                        disabled={deletingId === c.id}
                        data-testid={`task-comment-delete-${c.id}`}
                        className="text-destructive hover:bg-destructive/10"
                        aria-label="Xóa bình luận"
                      >
                        <span className="material-symbols-outlined text-sm">
                          delete
                        </span>
                      </Button>
                    </div>
                  )}
                </div>
                {isEditing ? (
                  <div className="flex flex-col gap-2">
                    <textarea
                      value={editingBody}
                      onChange={(e) => setEditingBody(e.target.value)}
                      data-testid={`task-comment-edit-input-${c.id}`}
                      className={TEXTAREA_CLASS}
                    />
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={cancelEdit}
                      >
                        Hủy
                      </Button>
                      <Button
                        size="sm"
                        disabled={savingEdit}
                        onClick={() => saveEdit(c.id)}
                        data-testid={`task-comment-save-edit-${c.id}`}
                        className="bg-primary text-primary-foreground hover:bg-primary/90"
                      >
                        {savingEdit ? "Đang lưu…" : "Lưu"}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-foreground whitespace-pre-wrap break-words">
                    {renderCommentBody(c.body)}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
