"use client";

import * as React from "react";
import { ApiError } from "@/lib/api";
import {
  FEATURE_AGILE_PHASE_2,
  FEATURE_AGILE_PHASE_5,
} from "@/lib/feature-flags";
import {
  cancelSprint,
  closeSprint,
  createSprint,
  deleteSprint,
  listSprints,
  startSprint,
  updateSprint,
} from "@/lib/task-api";
import type {
  Sprint,
  SprintStatus,
  TaskGovernanceAdvisory,
} from "@/lib/task-types";
import { formatTaskDate } from "@/lib/task-types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { GovernanceAdvisoryToast } from "@/components/tasks/governance-advisory-toast";

// Phase 2 (FEATURE_AGILE_PHASE_2) — Sprint management panel for a single
// TaskProject. Hidden entirely when the flag is OFF so legacy deployments
// stay untouched. Strings are hardcoded Vietnamese per the project decision
// to avoid pulling in an i18n framework.
//
// Lifecycle verbs use stable testids so Wave 2 QA can drive the panel
// without depending on Vietnamese copy.

type SprintPanelProps = {
  projectId: string;
  /**
   * Optional callback fired after a sprint lifecycle mutation succeeds, so
   * the parent (e.g. a task board) can refresh task lists whose sprint_id
   * may have been cleared by a close/delete.
   */
  onSprintsChanged?: () => void;
};

const STATUS_LABELS: Record<SprintStatus, string> = {
  planned: "Đã lên kế hoạch",
  active: "Đang chạy",
  completed: "Đã kết thúc",
  cancelled: "Đã hủy",
};

const STATUS_BADGE_CLASS: Record<SprintStatus, string> = {
  planned: "bg-secondary text-secondary-foreground",
  active: "bg-primary/15 text-primary",
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-100",
  cancelled: "bg-muted text-muted-foreground",
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

// Coerce a `YYYY-MM-DD` <input type="date"> value to the ISO datetime the
// backend `SprintCreate.start_date: datetime` field expects. Empty input
// round-trips to `null`.
function dateInputToIso(raw: string): string | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  // Use midnight UTC so the date stays stable across timezones — the backend
  // column is `date`, so the time component is dropped on persistence anyway.
  return `${trimmed}T00:00:00`;
}

// Convert backend ISO (`2026-06-01T00:00:00` or just `2026-06-01`) back to a
// `<input type="date">` value. Returns `""` for null/invalid.
function isoToDateInput(value: string | null | undefined): string {
  if (!value) return "";
  const [datePart] = value.split("T");
  return datePart ?? "";
}

function isFlagOn(): boolean {
  return FEATURE_AGILE_PHASE_2;
}

export function SprintPanel({ projectId, onSprintsChanged }: SprintPanelProps) {
  const [sprints, setSprints] = React.useState<Sprint[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string>("");
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Sprint | null>(null);
  // Phase 5: governance advisories returned from `closeSprint` when the
  // actor lacks `agile.sprint.close`. The close itself is NOT blocked.
  const [governanceAdvisories, setGovernanceAdvisories] = React.useState<
    TaskGovernanceAdvisory[]
  >([]);

  const refresh = React.useCallback(async () => {
    if (!isFlagOn()) return;
    setLoading(true);
    setError("");
    try {
      const items = await listSprints(projectId);
      setSprints(items);
    } catch (err) {
      setError(getErrorMessage(err, "Không tải được danh sách Sprint"));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  React.useEffect(() => {
    const timerId = window.setTimeout(() => {
      refresh();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [refresh]);

  if (!isFlagOn()) {
    // Phase 2 OFF — render nothing. Caller can still mount this component
    // unconditionally; the flag check lives here so the gate is co-located
    // with the feature.
    return null;
  }

  const handleSaved = async () => {
    setDialogOpen(false);
    setEditing(null);
    await refresh();
    onSprintsChanged?.();
  };

  const handleLifecycle = async (sprintId: string, action: SprintStatus | "delete") => {
    setError("");
    setGovernanceAdvisories([]);
    try {
      if (action === "active") {
        await startSprint(sprintId);
      } else if (action === "completed") {
        const result = await closeSprint(sprintId);
        // Phase 5: surface Stage A advisory toast when present. The close
        // already succeeded; the toast is a permission breadcrumb only.
        if (
          FEATURE_AGILE_PHASE_5 &&
          result.governance_advisories.length > 0
        ) {
          setGovernanceAdvisories(result.governance_advisories);
        }
      } else if (action === "cancelled") {
        await cancelSprint(sprintId);
      } else if (action === "delete") {
        await deleteSprint(sprintId);
      }
      await refresh();
      onSprintsChanged?.();
    } catch (err) {
      setError(getErrorMessage(err, "Cập nhật Sprint thất bại"));
    }
  };

  return (
    <section
      className="flex flex-col gap-3 rounded-xl border border-border bg-card/40 p-4"
      data-testid="sprint-panel"
    >
      <header className="flex items-center justify-between gap-2">
        <div className="flex flex-col">
          <h2 className="text-base font-semibold tracking-tight text-foreground">
            Sprint
          </h2>
          <p className="text-xs text-muted-foreground">
            Quản lý chu kỳ Sprint cho dự án này. Mỗi dự án chỉ có thể có một
            Sprint đang chạy.
          </p>
        </div>
        <Button
          data-testid="create-sprint-btn"
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
          className="bg-primary text-primary-foreground hover:bg-primary/90"
        >
          <span className="material-symbols-outlined mr-1 text-sm">add</span>
          Tạo Sprint
        </Button>
      </header>

      {error && (
        <div
          className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
          data-testid="sprint-panel-error"
        >
          {error}
        </div>
      )}

      <GovernanceAdvisoryToast
        advisories={governanceAdvisories}
        onDismiss={() => setGovernanceAdvisories([])}
      />

      {loading ? (
        <div className="text-sm text-muted-foreground">Đang tải Sprint…</div>
      ) : sprints.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-secondary/30 px-4 py-6 text-center text-sm text-muted-foreground">
          Chưa có Sprint nào. Bấm “Tạo Sprint” để bắt đầu.
        </div>
      ) : (
        <ul className="flex flex-col gap-2" data-testid="sprint-list">
          {sprints.map((sprint) => (
            <SprintRow
              key={sprint.id}
              sprint={sprint}
              onEdit={() => {
                setEditing(sprint);
                setDialogOpen(true);
              }}
              onLifecycle={(action) => handleLifecycle(sprint.id, action)}
            />
          ))}
        </ul>
      )}

      {dialogOpen && (
        <SprintFormDialog
          key={editing?.id ?? "new"}
          projectId={projectId}
          sprint={editing}
          open={dialogOpen}
          onOpenChange={(open) => {
            setDialogOpen(open);
            if (!open) setEditing(null);
          }}
          onSaved={handleSaved}
        />
      )}
    </section>
  );
}

type SprintRowProps = {
  sprint: Sprint;
  onEdit: () => void;
  onLifecycle: (action: SprintStatus | "delete") => void;
};

function SprintRow({ sprint, onEdit, onLifecycle }: SprintRowProps) {
  const canStart = sprint.status === "planned";
  const canClose = sprint.status === "active";
  const canCancel = sprint.status === "planned" || sprint.status === "active";
  const canDelete = sprint.status !== "active";

  return (
    <li
      className="flex flex-col gap-2 rounded-lg border border-border bg-background p-3"
      data-testid={`sprint-row-${sprint.id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-foreground">
              {sprint.name}
            </span>
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_BADGE_CLASS[sprint.status]}`}
            >
              {STATUS_LABELS[sprint.status]}
            </span>
          </div>
          {sprint.goal && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              <span className="font-medium">Mục tiêu Sprint: </span>
              {sprint.goal}
            </p>
          )}
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {formatTaskDate(sprint.start_date)} → {formatTaskDate(sprint.end_date)}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={onEdit}
            data-testid={`sprint-edit-${sprint.id}`}
          >
            Chỉnh sửa
          </Button>
          {canStart && (
            <Button
              size="sm"
              onClick={() => onLifecycle("active")}
              data-testid={`sprint-start-${sprint.id}`}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              Bắt đầu
            </Button>
          )}
          {canClose && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onLifecycle("completed")}
              data-testid={`sprint-close-${sprint.id}`}
            >
              Kết thúc
            </Button>
          )}
          {canCancel && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onLifecycle("cancelled")}
              data-testid={`sprint-cancel-${sprint.id}`}
            >
              Hủy Sprint
            </Button>
          )}
          {canDelete && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onLifecycle("delete")}
              data-testid={`sprint-delete-${sprint.id}`}
              className="text-destructive hover:bg-destructive/10"
            >
              Xóa
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}

type SprintFormDialogProps = {
  projectId: string;
  sprint: Sprint | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
};

function SprintFormDialog({
  projectId,
  sprint,
  open,
  onOpenChange,
  onSaved,
}: SprintFormDialogProps) {
  const [name, setName] = React.useState<string>(() => sprint?.name ?? "");
  const [goal, setGoal] = React.useState<string>(() => sprint?.goal ?? "");
  const [startDate, setStartDate] = React.useState<string>(() =>
    isoToDateInput(sprint?.start_date),
  );
  const [endDate, setEndDate] = React.useState<string>(() =>
    isoToDateInput(sprint?.end_date),
  );
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string>("");

  const handleSave = async () => {
    setError("");
    const trimmedName = name.trim();
    if (trimmedName === "") {
      setError("Tên Sprint không được để trống");
      return;
    }
    // Vietnamese client-side validation. The backend will also reject the
    // same case with code INVALID_DATE_RANGE, but catching it early keeps
    // the UX snappy and avoids a round-trip.
    if (startDate && endDate && startDate > endDate) {
      setError("Ngày bắt đầu phải trước ngày kết thúc");
      return;
    }

    setSaving(true);
    try {
      const body = {
        name: trimmedName,
        goal: goal.trim() === "" ? null : goal.trim(),
        start_date: dateInputToIso(startDate),
        end_date: dateInputToIso(endDate),
      };
      if (sprint) {
        await updateSprint(sprint.id, body);
      } else {
        await createSprint(projectId, body);
      }
      onSaved();
    } catch (err) {
      // Translate the documented server-side date-range error to Vietnamese.
      if (err instanceof ApiError && err.status === 409) {
        const detail = (err.data as { detail?: { code?: string } } | null)?.detail;
        if (detail?.code === "INVALID_DATE_RANGE") {
          setError("Ngày bắt đầu phải trước ngày kết thúc");
          setSaving(false);
          return;
        }
        if (detail?.code === "ACTIVE_SPRINT_EXISTS") {
          setError("Dự án đã có một Sprint đang chạy");
          setSaving(false);
          return;
        }
      }
      setError(getErrorMessage(err, "Lưu Sprint thất bại"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="sprint-form-dialog">
        <DialogHeader>
          <DialogTitle className="text-xl">
            {sprint ? "Chỉnh sửa Sprint" : "Tạo Sprint mới"}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-2 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sprint-name-input">Tên Sprint</Label>
            <Input
              id="sprint-name-input"
              data-testid="sprint-name-input"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Sprint Thử Nghiệm 1"
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sprint-goal-input">Mục tiêu Sprint</Label>
            <Textarea
              id="sprint-goal-input"
              data-testid="sprint-goal-input"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              placeholder="Mô tả ngắn gọn kết quả Sprint cần đạt được."
              rows={3}
              className="bg-background"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sprint-start-date-input">Ngày bắt đầu</Label>
              <Input
                id="sprint-start-date-input"
                data-testid="sprint-start-date-input"
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
                className="bg-background"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sprint-end-date-input">Ngày kết thúc</Label>
              <Input
                id="sprint-end-date-input"
                data-testid="sprint-end-date-input"
                type="date"
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
                className="bg-background"
              />
            </div>
          </div>

          {error && (
            <p
              className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
              role="alert"
              data-testid="sprint-form-error"
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
              data-testid="sprint-save-btn"
              disabled={saving}
              onClick={handleSave}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? "Đang lưu…" : "Lưu Sprint"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
