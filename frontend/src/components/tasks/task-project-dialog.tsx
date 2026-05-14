"use client";

import React from "react";
import { ApiError } from "@/lib/api";
import { createTaskProject, updateTaskProject } from "@/lib/task-api";
import type { TaskProject } from "@/lib/task-types";
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

export type ScopeOption = { id: string; name: string };

type ScopeKind = "workspace" | "department";

type TaskProjectDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: TaskProject | null;
  workspaces: ScopeOption[];
  departments: ScopeOption[];
  onSaved: () => void;
  // Pre-fill scope when opening from a scoped context (e.g. department hub).
  // Ignored in edit mode; project values win.
  initialScope?: ScopeKind;
  initialDepartmentId?: string;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function inferScope(project: TaskProject | null): ScopeKind {
  if (project?.department_id) return "department";
  return "workspace";
}

export function TaskProjectDialog({
  open,
  onOpenChange,
  project,
  workspaces,
  departments,
  onSaved,
  initialScope,
  initialDepartmentId,
}: TaskProjectDialogProps) {
  const isEdit = project !== null;

  // Lazy initial state derived from props. The parent re-mounts the dialog
  // (via `key`) whenever `project` switches, which keeps inputs aligned
  // without resorting to setState-in-effect.
  const [name, setName] = React.useState(() => project?.name ?? "");
  const [identifier, setIdentifier] = React.useState(
    () => project?.identifier ?? ""
  );
  const [description, setDescription] = React.useState(
    () => project?.description ?? ""
  );
  const [scopeKind, setScopeKind] = React.useState<ScopeKind>(() =>
    isEdit ? inferScope(project) : initialScope ?? inferScope(project)
  );
  const [workspaceId, setWorkspaceId] = React.useState(
    () => project?.workspace_id ?? ""
  );
  const [departmentId, setDepartmentId] = React.useState(() =>
    isEdit ? project?.department_id ?? "" : initialDepartmentId ?? ""
  );
  const [allowAnyEmployee, setAllowAnyEmployee] = React.useState(
    () => project?.allow_any_employee ?? false
  );
  const [archived, setArchived] = React.useState(
    () => project?.is_archived ?? false
  );
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");

  const handleScopeChange = (kind: ScopeKind) => {
    setScopeKind(kind);
    if (kind === "workspace") {
      setDepartmentId("");
    } else {
      setWorkspaceId("");
    }
  };

  const handleSave = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Tên dự án là bắt buộc");
      return;
    }

    if (!isEdit) {
      const trimmedIdentifier = identifier.trim().toUpperCase();
      if (!trimmedIdentifier) {
        setError("Mã định danh là bắt buộc");
        return;
      }
      if (!/^[A-Z0-9_]+$/.test(trimmedIdentifier)) {
        setError("Mã định danh chỉ chứa chữ HOA, số và dấu gạch dưới");
        return;
      }
      const hasWorkspace = scopeKind === "workspace" && workspaceId !== "";
      const hasDepartment = scopeKind === "department" && departmentId !== "";
      if (!hasWorkspace && !hasDepartment) {
        setError("Chỉ chọn một phạm vi: không gian nghiệp vụ hoặc đơn vị");
        return;
      }
    }

    setSaving(true);
    setError("");
    try {
      if (isEdit && project) {
        await updateTaskProject(project.id, {
          name: trimmedName,
          description: description.trim() || null,
          allow_any_employee: allowAnyEmployee,
          is_archived: archived,
        });
      } else {
        await createTaskProject({
          name: trimmedName,
          identifier: identifier.trim().toUpperCase(),
          description: description.trim() || null,
          workspace_id: scopeKind === "workspace" ? workspaceId : null,
          department_id: scopeKind === "department" ? departmentId : null,
          allow_any_employee: allowAnyEmployee,
        });
      }
      onSaved();
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, "Lưu dự án thất bại"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-xl">
            {isEdit ? "Chỉnh sửa dự án công việc" : "Tạo dự án công việc"}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="task-project-name">Tên dự án</Label>
            <Input
              id="task-project-name"
              data-testid="task-project-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: Triển khai khách hàng SME"
              className="bg-background"
            />
          </div>

          {!isEdit && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="task-project-identifier">Mã định danh</Label>
              <Input
                id="task-project-identifier"
                data-testid="task-project-identifier-input"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value.toUpperCase())}
                placeholder="VD: SME, OPS_2026"
                className="bg-background uppercase tracking-wide"
                maxLength={32}
              />
              <p className="text-xs text-muted-foreground">
                Chữ HOA, số và dấu gạch dưới — sẽ là tiền tố cho mã công việc.
              </p>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="task-project-description">
              Mô tả{" "}
              <span className="text-muted-foreground font-normal">
                (tuỳ chọn)
              </span>
            </Label>
            <Textarea
              id="task-project-description"
              data-testid="task-project-description-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Mục tiêu, phạm vi hoặc ghi chú vận hành"
              className="min-h-20 bg-background"
            />
          </div>

          {!isEdit && (
            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium">Phạm vi</span>
              <p className="text-xs text-muted-foreground">
                Chỉ chọn một phạm vi. Dự án thuộc về một không gian nghiệp vụ
                HOẶC một đơn vị, không cả hai.
              </p>
              <div
                className="grid grid-cols-2 gap-2"
                role="radiogroup"
                aria-label="Phạm vi dự án"
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={scopeKind === "workspace"}
                  data-testid="task-project-scope-workspace"
                  onClick={() => handleScopeChange("workspace")}
                  className={`flex flex-col items-start gap-1 rounded-lg border px-3 py-2 text-left transition-colors ${
                    scopeKind === "workspace"
                      ? "border-primary bg-primary/5"
                      : "border-border bg-background hover:bg-muted/40"
                  }`}
                >
                  <span className="flex items-center gap-1.5 text-sm font-medium">
                    <span className="material-symbols-outlined text-base">
                      workspaces
                    </span>
                    Không gian nghiệp vụ
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Cho thành viên của workspace.
                  </span>
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={scopeKind === "department"}
                  data-testid="task-project-scope-department"
                  onClick={() => handleScopeChange("department")}
                  className={`flex flex-col items-start gap-1 rounded-lg border px-3 py-2 text-left transition-colors ${
                    scopeKind === "department"
                      ? "border-primary bg-primary/5"
                      : "border-border bg-background hover:bg-muted/40"
                  }`}
                >
                  <span className="flex items-center gap-1.5 text-sm font-medium">
                    <span className="material-symbols-outlined text-base">
                      domain
                    </span>
                    Đơn vị
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Cho nhân viên thuộc đơn vị.
                  </span>
                </button>
              </div>

              {scopeKind === "workspace" ? (
                <div className="flex flex-col gap-1.5">
                  <Label>Chọn không gian nghiệp vụ</Label>
                  <Select
                    value={workspaceId}
                    onValueChange={(v) => setWorkspaceId(v ?? "")}
                  >
                    <SelectTrigger
                      data-testid="task-project-workspace-select"
                      className="w-full bg-background"
                    >
                      {workspaceId ? (
                        <span className="truncate">
                          {workspaces.find((w) => w.id === workspaceId)?.name ??
                            workspaceId}
                        </span>
                      ) : (
                        <SelectValue placeholder="Chọn không gian" />
                      )}
                    </SelectTrigger>
                    <SelectContent>
                      {workspaces.length === 0 ? (
                        <div className="px-3 py-2 text-xs text-muted-foreground">
                          Chưa có không gian nào khả dụng
                        </div>
                      ) : (
                        workspaces.map((w) => (
                          <SelectItem key={w.id} value={w.id}>
                            {w.name}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  <Label>Chọn đơn vị</Label>
                  <Select
                    value={departmentId}
                    onValueChange={(v) => setDepartmentId(v ?? "")}
                  >
                    <SelectTrigger
                      data-testid="task-project-department-select"
                      className="w-full bg-background"
                    >
                      {departmentId ? (
                        <span className="truncate">
                          {departments.find((d) => d.id === departmentId)
                            ?.name ?? departmentId}
                        </span>
                      ) : (
                        <SelectValue placeholder="Chọn đơn vị" />
                      )}
                    </SelectTrigger>
                    <SelectContent>
                      {departments.length === 0 ? (
                        <div className="px-3 py-2 text-xs text-muted-foreground">
                          Chưa có đơn vị nào khả dụng
                        </div>
                      ) : (
                        departments.map((d) => (
                          <SelectItem key={d.id} value={d.id}>
                            {d.name}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          )}

          <label className="flex items-start gap-2 rounded-lg border border-border bg-background p-3 cursor-pointer hover:bg-muted/40 transition-colors">
            <input
              type="checkbox"
              checked={allowAnyEmployee}
              onChange={(e) => setAllowAnyEmployee(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-input"
              data-testid="task-project-allow-any-employee"
            />
            <span className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">
                Cho phép giao cho tất cả nhân viên
              </span>
              <span className="text-xs text-muted-foreground">
                Mở rộng quyền giao việc cho mọi nhân viên đang hoạt động, không
                giới hạn theo phạm vi.
              </span>
            </span>
          </label>

          {isEdit && (
            <label className="flex items-start gap-2 rounded-lg border border-border bg-background p-3 cursor-pointer hover:bg-muted/40 transition-colors">
              <input
                type="checkbox"
                checked={archived}
                onChange={(e) => setArchived(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-input"
                data-testid="task-project-archived-toggle"
              />
              <span className="flex flex-col gap-0.5">
                <span className="text-sm font-medium">Đã lưu trữ</span>
                <span className="text-xs text-muted-foreground">
                  Dự án đã lưu trữ chỉ hiện khi bật bộ lọc và không cho phép
                  thay đổi công việc bên trong.
                </span>
              </span>
            </label>
          )}

          {error && (
            <p
              className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
              data-testid="task-project-form-error"
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
              data-testid="task-project-save-btn"
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
