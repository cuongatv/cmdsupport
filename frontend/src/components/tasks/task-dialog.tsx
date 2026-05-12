"use client";

import React from "react";
import { ApiError } from "@/lib/api";
import { createTask, createTaskInScope, updateTask } from "@/lib/task-api";
import type {
  EligibleAssignee,
  Task,
  TaskCreate,
  TaskLabel,
  TaskPriority,
  TaskProject,
  TaskScope,
  TaskState,
  TaskUpdate,
} from "@/lib/task-types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { translateStateName } from "@/lib/task-i18n";

const PRIORITY_OPTIONS: Array<{ value: TaskPriority; label: string }> = [
  { value: "none", label: "Không có" },
  { value: "low", label: "Thấp" },
  { value: "medium", label: "Trung bình" },
  { value: "high", label: "Cao" },
  { value: "urgent", label: "Khẩn cấp" },
];

// Sentinel value used by base-ui Select since SelectItem rejects empty string.
const NONE_VALUE = "__none__";

export type TaskDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task: Task | null;
  // `project` is required for edit and for project-context create flows
  // (Kanban, project dashboard). When the user is creating from the scope
  // filter only (Không gian làm việc / Phòng ban), pass `scope` instead and
  // leave `project` null — the backend resolves the hidden default project.
  project: TaskProject | null;
  scope?: TaskScope | null;
  scopeLabel?: string;
  states: TaskState[];
  labels: TaskLabel[];
  eligibleAssignees: EligibleAssignee[];
  parentCandidates: Task[];
  defaultParentTaskId?: string | null;
  onSaved: (task: Task) => void;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return "công việc đã được cập nhật bởi người khác";
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

function dueDateToInputValue(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function inputValueToDueDate(value: string): string | null {
  if (!value) return null;
  // End of day UTC keeps the visible date stable across timezones.
  return `${value}T23:59:59.000Z`;
}

export function TaskDialog({
  open,
  onOpenChange,
  task,
  project,
  scope = null,
  scopeLabel,
  states,
  labels,
  eligibleAssignees,
  parentCandidates,
  defaultParentTaskId = null,
  onSaved,
}: TaskDialogProps) {
  const isEdit = task !== null;
  // Scope-only create: user picked a Không gian làm việc / Phòng ban but no
  // project. We hide state/label/assignee/parent pickers because those are
  // project-scoped and we don't have a project yet — the backend will resolve
  // the hidden default project and apply its default state.
  const isScopeCreate = !isEdit && project === null && scope !== null;

  // Lazy initial state derived from props. Parent re-mounts the dialog via
  // `key` whenever the task switches, so no setState-in-effect reset needed.
  const [title, setTitle] = React.useState(() => task?.title ?? "");
  const [description, setDescription] = React.useState(
    () => task?.description ?? ""
  );
  const [priority, setPriority] = React.useState<TaskPriority>(
    () => task?.priority ?? "none"
  );
  const [stateId, setStateId] = React.useState(
    () => task?.state_id ?? states[0]?.id ?? ""
  );
  // Reporter (Người báo cáo) was removed from the task UI per product decision —
  // the create/edit dialog no longer surfaces it. We still send the field on
  // update so existing values are preserved (null clears it, undefined leaves
  // it untouched by Pydantic exclude_unset on the server).
  const [parentTaskId, setParentTaskId] = React.useState(
    () => task?.parent_task_id ?? defaultParentTaskId ?? ""
  );
  const [dueDateInput, setDueDateInput] = React.useState(() =>
    dueDateToInputValue(task?.due_date)
  );
  const [assigneeIds, setAssigneeIds] = React.useState<string[]>([]);
  const [labelIds, setLabelIds] = React.useState<string[]>([]);

  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");

  const toggleAssignee = (id: string) => {
    setAssigneeIds((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    );
  };

  const toggleLabel = (id: string) => {
    setLabelIds((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    );
  };

  const handleSave = async () => {
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setError("Tên công việc là bắt buộc");
      return;
    }
    // State picker is only shown for project-context flows. Scope-create lets
    // the backend pick the default state of the resolved project.
    if (!isScopeCreate && !stateId) {
      setError("Chọn trạng thái cho công việc");
      return;
    }

    setSaving(true);
    setError("");

    try {
      let saved: Task;
      if (isEdit && task) {
        const updateBody: TaskUpdate = {
          version: task.version,
          title: trimmedTitle,
          description: description.trim() || null,
          priority,
          state_id: stateId,
          // reporter_id intentionally omitted — left untouched server-side.
          parent_task_id: parentTaskId || null,
          due_date: inputValueToDueDate(dueDateInput),
        };
        saved = await updateTask(task.id, updateBody);
      } else if (isScopeCreate && scope) {
        // Minimal payload: scope-based create skips project-scoped pickers
        // (state/labels/assignees/parent). Those can be filled later from the
        // task detail panel once the task lands in the resolved project.
        const createBody: TaskCreate = {
          title: trimmedTitle,
          description: description.trim() || null,
          priority,
          due_date: inputValueToDueDate(dueDateInput),
        };
        saved = await createTaskInScope(scope, createBody);
      } else if (project) {
        const createBody: TaskCreate = {
          title: trimmedTitle,
          description: description.trim() || null,
          priority,
          state_id: stateId,
          parent_task_id: parentTaskId || null,
          due_date: inputValueToDueDate(dueDateInput),
          assignee_ids: assigneeIds,
          label_ids: labelIds,
        };
        saved = await createTask(project.id, createBody);
      } else {
        setError("Thiếu phạm vi để tạo công việc");
        return;
      }
      onSaved(saved);
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, "Lưu công việc thất bại"));
    } finally {
      setSaving(false);
    }
  };


  const parentOptions = parentCandidates.filter((p) => p.id !== task?.id);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl">
            {isEdit ? "Chỉnh sửa công việc" : "Tạo công việc"}
          </DialogTitle>
          {!isEdit && scopeLabel ? (
            <p
              className="text-xs text-muted-foreground"
              data-testid="task-dialog-scope-hint"
            >
              Phạm vi: <span className="font-medium">{scopeLabel}</span>
            </p>
          ) : null}
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="task-dialog-title">Tên công việc</Label>
            <Input
              id="task-dialog-title"
              name="title"
              data-testid="task-dialog-title-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="VD: Soạn thảo hợp đồng cho khách hàng A"
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="task-dialog-description">
              Mô tả{" "}
              <span className="text-muted-foreground font-normal">
                (tuỳ chọn)
              </span>
            </Label>
            <Textarea
              id="task-dialog-description"
              data-testid="task-dialog-description-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Chi tiết, mục tiêu hoặc lưu ý quan trọng"
              className="min-h-24 bg-background"
            />
          </div>

          <div
            className={
              isScopeCreate
                ? "flex flex-col gap-3"
                : "grid grid-cols-1 sm:grid-cols-2 gap-3"
            }
          >
            {!isScopeCreate && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="task-dialog-state">Trạng thái xử lý</Label>
              <Select
                value={stateId}
                onValueChange={(v) => setStateId(v ?? "")}
              >
                <SelectTrigger
                  id="task-dialog-state"
                  data-testid="task-dialog-state-select"
                  className="w-full bg-background"
                >
                  {stateId ? (
                    (() => {
                      const stateName =
                        states.find((s) => s.id === stateId)?.name ?? stateId;
                      const display = translateStateName(stateName);
                      return (
                        <span
                          className="truncate max-w-[220px]"
                          title={display}
                        >
                          {display}
                        </span>
                      );
                    })()
                  ) : (
                    <SelectValue placeholder="Chọn trạng thái" />
                  )}
                </SelectTrigger>
                <SelectContent>
                  {states.length === 0 ? (
                    <div className="px-3 py-2 text-xs text-muted-foreground">
                      Chưa có trạng thái nào
                    </div>
                  ) : (
                    states.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {translateStateName(s.name)}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
            )}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="task-dialog-priority">Mức độ ưu tiên</Label>
              <Select
                value={priority}
                onValueChange={(v) =>
                  setPriority((v as TaskPriority) ?? "none")
                }
              >
                <SelectTrigger
                  id="task-dialog-priority"
                  data-testid="task-dialog-priority-select"
                  className="w-full bg-background"
                >
                  {(() => {
                    const display =
                      PRIORITY_OPTIONS.find((p) => p.value === priority)
                        ?.label ?? priority;
                    return (
                      <span
                        className="truncate max-w-[220px]"
                        title={display}
                      >
                        {display}
                      </span>
                    );
                  })()}
                </SelectTrigger>
                <SelectContent>
                  {PRIORITY_OPTIONS.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="task-dialog-due-date">Ngày hết hạn</Label>
            <Input
              id="task-dialog-due-date"
              name="target_date"
              data-testid="task-dialog-due-date-input"
              type="date"
              value={dueDateInput}
              onChange={(e) => setDueDateInput(e.target.value)}
              className="bg-background"
            />
          </div>

          {!isScopeCreate && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="task-dialog-parent">Công việc cha</Label>
            <Select
              value={parentTaskId || NONE_VALUE}
              onValueChange={(v) =>
                setParentTaskId(v === NONE_VALUE ? "" : v ?? "")
              }
            >
              <SelectTrigger
                id="task-dialog-parent"
                data-testid="task-dialog-parent-select"
                className="w-full bg-background"
              >
                {parentTaskId ? (
                  (() => {
                    const display =
                      parentOptions.find((p) => p.id === parentTaskId)?.title ??
                      parentTaskId;
                    return (
                      <span
                        className="truncate max-w-[460px]"
                        title={display}
                      >
                        {display}
                      </span>
                    );
                  })()
                ) : (
                  <SelectValue placeholder="Không có (công việc gốc)" />
                )}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE_VALUE}>
                  Không có (công việc gốc)
                </SelectItem>
                {parentOptions.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-muted-foreground">
                    Chưa có công việc gốc nào
                  </div>
                ) : (
                  parentOptions.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      <span className="truncate">{p.title}</span>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Chỉ chọn công việc gốc — không cho phép tạo nhiệm vụ con của
              nhiệm vụ con.
            </p>
          </div>
          )}

          {!isEdit && !isScopeCreate && project && (
            <div className="flex flex-col gap-1.5">
              <Label>Người được giao</Label>
              <p className="text-xs text-muted-foreground">
                {project.allow_any_employee
                  ? "Tất cả nhân viên đang hoạt động được phép giao việc."
                  : "Chỉ thành viên thuộc phạm vi dự án."}
              </p>
              <div
                className="max-h-44 overflow-y-auto rounded-lg border border-border bg-background p-1"
                data-testid="task-dialog-assignee-list"
              >
                {eligibleAssignees.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-2 px-2 text-center">
                    Chưa có nhân viên nào khả dụng
                  </p>
                ) : (
                  <div className="flex flex-col">
                    {eligibleAssignees.map((emp) => {
                      const checked = assigneeIds.includes(emp.id);
                      return (
                        <label
                          key={emp.id}
                          className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/40 cursor-pointer"
                          data-testid={`task-dialog-assignee-${emp.id}`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleAssignee(emp.id)}
                            className="h-4 w-4 rounded border-input"
                          />
                          <span className="flex flex-col min-w-0">
                            <span className="text-sm truncate">{emp.name}</span>
                            <span className="text-[11px] text-muted-foreground truncate">
                              {emp.email}
                            </span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {!isEdit && !isScopeCreate && labels.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label>Nhãn</Label>
              <div
                className="flex flex-wrap gap-1.5"
                data-testid="task-dialog-label-list"
              >
                {labels.map((label) => {
                  const checked = labelIds.includes(label.id);
                  return (
                    <button
                      type="button"
                      key={label.id}
                      onClick={() => toggleLabel(label.id)}
                      className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                        checked
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border bg-background text-muted-foreground hover:bg-muted/40"
                      }`}
                      data-testid={`task-dialog-label-${label.id}`}
                    >
                      {label.name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {isEdit && (
            <div className="rounded-lg border border-dashed border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
              Quản lý người được giao và nhãn ở chế độ chi tiết.
            </div>
          )}

          {isScopeCreate && (
            <div className="rounded-lg border border-dashed border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
              Công việc sẽ được tạo trong phạm vi đã chọn với trạng thái mặc
              định. Bạn có thể giao việc, gán nhãn hoặc đổi trạng thái sau khi
              mở chi tiết công việc.
            </div>
          )}

          {error && (
            <p
              className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
              data-testid="task-dialog-form-error"
              role="alert"
            >
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button
              disabled={saving}
              onClick={handleSave}
              data-testid="task-dialog-save-btn"
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? (
                <span className="flex items-center gap-2">
                  <span className="material-symbols-outlined animate-spin text-sm">
                    progress_activity
                  </span>
                  Đang lưu…
                </span>
              ) : (
                "Lưu"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
