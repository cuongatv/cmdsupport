"use client";

import * as React from "react";
import { ApiError } from "@/lib/api";
import { updateTaskState } from "@/lib/task-api";
import type { TaskState, WipPolicy } from "@/lib/task-types";
import { translateStateName } from "@/lib/task-i18n";
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

// Phase 1 (FEATURE_AGILE_PHASE_1) — Vietnamese WIP + aging configuration
// dialog for a single Kanban column (TaskState). Strings are hardcoded per
// the project decision to avoid pulling in an i18n framework.
//
// The dialog only renders when the caller decides the feature flag is ON;
// it does NOT re-check the flag itself so it stays trivially testable.

type TaskStateSettingsDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  state: TaskState;
  onSaved: (updated: TaskState) => void;
};

const POLICY_OPTIONS: ReadonlyArray<{ value: WipPolicy; label: string }> = [
  { value: "off", label: "Tắt — không kiểm tra" },
  { value: "warn", label: "Cảnh báo — vẫn cho phép di chuyển" },
  { value: "enforce", label: "Bắt buộc — chặn nếu vượt giới hạn" },
];

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

// Coerce a non-negative integer string back to a number-or-null. Empty input
// means "no limit" and must round-trip to `null` (so the backend treats it
// as "feature off for this column" rather than `0`, which means "block any
// in-flight task").
function parseOptionalCount(raw: string): { value: number | null; error: string | null } {
  const trimmed = raw.trim();
  if (trimmed === "") return { value: null, error: null };
  if (!/^\d+$/.test(trimmed)) {
    return { value: null, error: "Phải là số nguyên không âm" };
  }
  const parsed = Number.parseInt(trimmed, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return { value: null, error: "Phải là số nguyên không âm" };
  }
  return { value: parsed, error: null };
}

export function TaskStateSettingsDialog({
  open,
  onOpenChange,
  state,
  onSaved,
}: TaskStateSettingsDialogProps) {
  // Lazy initial state from props — the parent re-mounts via `key={state.id}`
  // whenever the active column changes, matching the pattern used in
  // task-project-dialog.tsx.
  const [wipLimitInput, setWipLimitInput] = React.useState<string>(() =>
    state.wip_limit === null || state.wip_limit === undefined
      ? ""
      : String(state.wip_limit),
  );
  const [wipPolicy, setWipPolicy] = React.useState<WipPolicy>(
    () => (state.wip_policy ?? "off") as WipPolicy,
  );
  const [agingInput, setAgingInput] = React.useState<string>(() =>
    state.aging_warn_days === null || state.aging_warn_days === undefined
      ? ""
      : String(state.aging_warn_days),
  );
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string>("");

  const handleSave = async () => {
    setError("");

    const wipLimitParsed = parseOptionalCount(wipLimitInput);
    if (wipLimitParsed.error) {
      setError(`Giới hạn việc đang làm: ${wipLimitParsed.error}`);
      return;
    }
    const agingParsed = parseOptionalCount(agingInput);
    if (agingParsed.error) {
      setError(`Ngày cảnh báo tồn đọng: ${agingParsed.error}`);
      return;
    }
    if (
      wipPolicy !== "off" &&
      (wipLimitParsed.value === null || wipLimitParsed.value === 0)
    ) {
      setError(
        "Khi bật chính sách Cảnh báo hoặc Bắt buộc, giới hạn việc đang làm phải lớn hơn 0.",
      );
      return;
    }

    setSaving(true);
    try {
      const updated = await updateTaskState(state.task_project_id, state.id, {
        wip_limit: wipLimitParsed.value,
        wip_policy: wipPolicy,
        aging_warn_days: agingParsed.value,
      });
      onSaved(updated);
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, "Lưu cấu hình Kanban thất bại"));
    } finally {
      setSaving(false);
    }
  };

  const columnName = translateStateName(state.name);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-md"
        data-testid="task-state-settings-dialog"
      >
        <DialogHeader>
          <DialogTitle className="text-xl">
            Cấu hình Kanban — {columnName}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-2 flex flex-col gap-4">
          <p className="text-xs text-muted-foreground">
            Cấu hình giới hạn việc đang làm (WIP) và cảnh báo tồn đọng cho cột
            Kanban này. Tính năng Phase 1 áp dụng theo từng cột.
          </p>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="wip-limit-input">Giới hạn việc đang làm</Label>
            <Input
              id="wip-limit-input"
              data-testid="wip-limit-input"
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              placeholder="Để trống nếu không giới hạn"
              value={wipLimitInput}
              onChange={(event) => setWipLimitInput(event.target.value)}
              className="bg-background"
            />
            <p className="text-xs text-muted-foreground">
              Số công việc tối đa được phép ở trạng thái này cùng lúc.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Chính sách giới hạn</Label>
            <Select
              value={wipPolicy}
              onValueChange={(value) => {
                if (value) setWipPolicy(value as WipPolicy);
              }}
            >
              <SelectTrigger
                data-testid="wip-policy-select"
                className="w-full bg-background"
              >
                <SelectValue placeholder="Chọn chính sách" />
              </SelectTrigger>
              <SelectContent>
                {POLICY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Cảnh báo: hiển thị thông báo nhưng vẫn cho phép. Bắt buộc: chặn
              di chuyển khi vượt giới hạn.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="aging-warn-days-input">
              Ngày cảnh báo tồn đọng
            </Label>
            <Input
              id="aging-warn-days-input"
              data-testid="aging-warn-days-input"
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              placeholder="Để trống nếu không cảnh báo"
              value={agingInput}
              onChange={(event) => setAgingInput(event.target.value)}
              className="bg-background"
            />
            <p className="text-xs text-muted-foreground">
              Số ngày tối đa công việc được phép tồn đọng trước khi gắn cờ.
            </p>
          </div>

          {error && (
            <p
              className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
              role="alert"
              data-testid="task-state-settings-error"
            >
              {error}
            </p>
          )}

          <div className="mt-2 flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={saving}
            >
              Hủy
            </Button>
            <Button
              data-testid="save-state-settings-btn"
              disabled={saving}
              onClick={handleSave}
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
                "Lưu cấu hình Kanban"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
