"use client";

import React from "react";
import { ApiError } from "@/lib/api";
import {
  forwardTask,
  listDepartmentMembers,
  listDepartments,
} from "@/lib/task-api";
import type {
  DepartmentMember,
  DepartmentSummary,
  Task,
} from "@/lib/task-types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type ForwardMode = "same_unit" | "cross_unit";

export type TaskForwardDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task: Task;
  /** Department id of the current task, if known. Used for same-unit member fetch. */
  sourceDepartmentId: string | null;
  currentAssigneeIds: string[];
  currentUserId: string | null;
  onForwarded: () => void;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export function TaskForwardDialog({
  open,
  onOpenChange,
  task,
  sourceDepartmentId,
  currentAssigneeIds,
  currentUserId,
  onForwarded,
}: TaskForwardDialogProps) {
  const [mode, setMode] = React.useState<ForwardMode>("same_unit");
  const [departments, setDepartments] = React.useState<DepartmentSummary[]>([]);
  const [departmentsLoading, setDepartmentsLoading] = React.useState(false);
  const [targetDeptId, setTargetDeptId] = React.useState<string>("");
  const [members, setMembers] = React.useState<DepartmentMember[]>([]);
  const [membersLoading, setMembersLoading] = React.useState(false);
  const [assigneeId, setAssigneeId] = React.useState<string>("");
  const [reason, setReason] = React.useState("");
  const [keepPrev, setKeepPrev] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState("");

  // Reset on open.
  React.useEffect(() => {
    if (!open) return;
    setMode("same_unit");
    setTargetDeptId("");
    setAssigneeId("");
    setReason("");
    setKeepPrev(false);
    setError("");
  }, [open]);

  // Load departments when entering cross_unit mode.
  React.useEffect(() => {
    if (!open || mode !== "cross_unit" || departments.length > 0) return;
    setDepartmentsLoading(true);
    listDepartments()
      .then((rows) => {
        const filtered = rows.filter(
          (d) => !d.is_archived && d.id !== sourceDepartmentId,
        );
        setDepartments(filtered);
      })
      .catch((err) =>
        setError(getErrorMessage(err, "Không tải được danh sách đơn vị")),
      )
      .finally(() => setDepartmentsLoading(false));
  }, [open, mode, departments.length, sourceDepartmentId]);

  // Load members whenever the effective department changes.
  const effectiveDeptId =
    mode === "same_unit" ? sourceDepartmentId : targetDeptId;

  React.useEffect(() => {
    if (!open || !effectiveDeptId) {
      setMembers([]);
      setAssigneeId("");
      return;
    }
    setMembersLoading(true);
    setAssigneeId("");
    listDepartmentMembers(effectiveDeptId)
      .then((rows) => {
        const filtered = rows.filter(
          (m) =>
            m.is_active &&
            m.employee_id !== currentUserId &&
            !(
              !keepPrev &&
              currentAssigneeIds.length === 1 &&
              currentAssigneeIds[0] === m.employee_id
            ),
        );
        setMembers(filtered);
      })
      .catch((err) =>
        setError(getErrorMessage(err, "Không tải được thành viên đơn vị")),
      )
      .finally(() => setMembersLoading(false));
    // Re-run when assignee list or keepPrev shape changes meaningfully.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, effectiveDeptId]);

  const canSubmit =
    assigneeId.length > 0 &&
    reason.trim().length >= 10 &&
    !submitting &&
    (mode === "same_unit" || targetDeptId.length > 0);

  const handleSubmit = async () => {
    setError("");
    setSubmitting(true);
    try {
      await forwardTask(task.id, {
        target_department_id: mode === "same_unit" ? null : targetDeptId,
        new_assignee_id: assigneeId,
        reason: reason.trim(),
        keep_previous_assignees: keepPrev,
        version: task.version,
      });
      onForwarded();
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, "Chuyển tiếp công việc thất bại"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Chuyển tiếp công việc</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2">
          {error && (
            <p
              className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
              role="alert"
              data-testid="task-forward-error"
            >
              {error}
            </p>
          )}

          <fieldset className="flex flex-col gap-2">
            <legend className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
              Phạm vi chuyển tiếp
            </legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="forward-mode"
                value="same_unit"
                checked={mode === "same_unit"}
                onChange={() => setMode("same_unit")}
                disabled={!sourceDepartmentId}
              />
              Trong cùng đơn vị
              {!sourceDepartmentId && (
                <span className="text-xs text-muted-foreground">
                  (không xác định được đơn vị nguồn — chọn đơn vị khác)
                </span>
              )}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="forward-mode"
                value="cross_unit"
                checked={mode === "cross_unit"}
                onChange={() => setMode("cross_unit")}
              />
              Sang đơn vị khác
            </label>
          </fieldset>

          {mode === "cross_unit" && (
            <div className="flex flex-col gap-1.5">
              <label
                className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground"
                htmlFor="forward-dept"
              >
                Đơn vị đích
              </label>
              <select
                id="forward-dept"
                className="rounded-md border border-border bg-background px-2.5 py-1.5 text-sm"
                value={targetDeptId}
                onChange={(e) => setTargetDeptId(e.target.value)}
                disabled={departmentsLoading}
                data-testid="task-forward-dept"
              >
                <option value="">
                  {departmentsLoading
                    ? "Đang tải đơn vị…"
                    : "— Chọn đơn vị —"}
                </option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label
              className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground"
              htmlFor="forward-assignee"
            >
              Người được giao
            </label>
            <select
              id="forward-assignee"
              className="rounded-md border border-border bg-background px-2.5 py-1.5 text-sm"
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
              disabled={
                membersLoading || !effectiveDeptId || members.length === 0
              }
              data-testid="task-forward-assignee"
            >
              <option value="">
                {!effectiveDeptId
                  ? "— Chọn đơn vị trước —"
                  : membersLoading
                    ? "Đang tải thành viên…"
                    : members.length === 0
                      ? "Không có thành viên khả dụng"
                      : "— Chọn người được giao —"}
              </option>
              {members.map((m) => (
                <option key={m.employee_id} value={m.employee_id}>
                  {m.employee_name ?? m.employee_id} ({m.role})
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground"
              htmlFor="forward-reason"
            >
              Lý do chuyển tiếp (bắt buộc, ít nhất 10 ký tự)
            </label>
            <textarea
              id="forward-reason"
              className="rounded-md border border-border bg-background px-2.5 py-1.5 text-sm min-h-20"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={2000}
              data-testid="task-forward-reason"
            />
            <span className="text-[11px] text-muted-foreground">
              {reason.trim().length}/10 ký tự tối thiểu
            </span>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={keepPrev}
              onChange={(e) => setKeepPrev(e.target.checked)}
              data-testid="task-forward-keep-prev"
            />
            Giữ lại người được giao hiện tại (chế độ bàn giao có giám sát)
          </label>
        </div>

        <DialogFooter className="mt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Hủy
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!canSubmit}
            data-testid="task-forward-submit"
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            {submitting ? "Đang chuyển tiếp…" : "Chuyển tiếp"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
