"use client";

import * as React from "react";
import { ApiError } from "@/lib/api";
import { FEATURE_AGILE_PHASE_2 } from "@/lib/feature-flags";
import {
  addTaskDependency,
  listSprints,
  listTaskDependencies,
  removeTaskDependency,
  updateTaskSemantics,
} from "@/lib/task-api";
import type {
  EstimateSize,
  Sprint,
  Task,
  TaskDependency,
  TaskType,
} from "@/lib/task-types";
import { formatTaskDateTime } from "@/lib/task-types";
import { Button } from "@/components/ui/button";
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

// Phase 2 (FEATURE_AGILE_PHASE_2) — Vietnamese task semantics panel.
// Render this inside the task detail view; it is hidden entirely when the
// feature flag is OFF. Mutations go through `updateTaskSemantics` (PATCH
// /tasks/{id}) which preserves optimistic concurrency via `version`.

type ChecklistItem = {
  id: string;
  label: string;
  done: boolean;
};

type TaskSemanticsPanelProps = {
  task: Task;
  /**
   * Called after a successful PATCH so the parent can re-render with the
   * fresh task (which carries the bumped `version`).
   */
  onTaskUpdated: (updated: Task) => void;
};

const TASK_TYPE_LABELS: Record<TaskType, string> = {
  story: "User Story",
  task: "Công việc",
  bug: "Lỗi (Bug)",
  epic: "Epic",
  spike: "Khảo sát (Spike)",
};

const ESTIMATE_LABELS: Record<EstimateSize, string> = {
  xs: "XS — Rất nhỏ",
  s: "S — Nhỏ",
  m: "M — Trung bình",
  l: "L — Lớn",
  xl: "XL — Rất lớn",
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

// Coerce a server-emitted checklist (`list[Any]`) into a stable, editable
// shape. Each item gains a synthetic `id` so React keys stay stable across
// re-renders even if the user toggles `done` repeatedly.
function normalizeChecklist(raw: unknown): ChecklistItem[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((entry, index) => {
    if (entry && typeof entry === "object") {
      const obj = entry as Record<string, unknown>;
      const label = typeof obj.label === "string"
        ? obj.label
        : typeof obj.text === "string"
          ? obj.text
          : String(obj.label ?? obj.text ?? "");
      const done = Boolean(obj.done);
      return { id: `c-${index}`, label, done };
    }
    return { id: `c-${index}`, label: String(entry ?? ""), done: false };
  });
}

function serializeChecklist(items: ChecklistItem[]): { label: string; done: boolean }[] {
  return items.map((item) => ({ label: item.label, done: item.done }));
}

export function TaskSemanticsPanel({ task, onTaskUpdated }: TaskSemanticsPanelProps) {
  // Local edit state — initialised from the task prop and kept in sync via
  // the `setTimeout(0)` workaround the project uses everywhere to dodge
  // `react-hooks/set-state-in-effect`.
  const [taskType, setTaskType] = React.useState<TaskType | "none">(
    () => (task.task_type ?? "none") as TaskType | "none",
  );
  const [estimate, setEstimate] = React.useState<EstimateSize | "none">(
    () => (task.estimate ?? "none") as EstimateSize | "none",
  );
  const [storyPoints, setStoryPoints] = React.useState<string>(() =>
    task.story_points === null || task.story_points === undefined
      ? ""
      : String(task.story_points),
  );
  const [acceptanceCriteria, setAcceptanceCriteria] = React.useState<string>(
    () => task.acceptance_criteria ?? "",
  );
  const [dor, setDor] = React.useState<ChecklistItem[]>(() =>
    normalizeChecklist(task.dor_checklist),
  );
  const [dod, setDod] = React.useState<ChecklistItem[]>(() =>
    normalizeChecklist(task.dod_checklist),
  );
  const [blockedReason, setBlockedReason] = React.useState<string>(
    () => task.blocked_reason ?? "",
  );
  const [sprintId, setSprintId] = React.useState<string>(
    () => task.sprint_id ?? "none",
  );

  const [sprints, setSprints] = React.useState<Sprint[]>([]);
  const [dependencies, setDependencies] = React.useState<TaskDependency[]>([]);
  const [newDepId, setNewDepId] = React.useState<string>("");
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string>("");
  const [info, setInfo] = React.useState<string>("");

  React.useEffect(() => {
    const timerId = window.setTimeout(() => {
      setTaskType((task.task_type ?? "none") as TaskType | "none");
      setEstimate((task.estimate ?? "none") as EstimateSize | "none");
      setStoryPoints(
        task.story_points === null || task.story_points === undefined
          ? ""
          : String(task.story_points),
      );
      setAcceptanceCriteria(task.acceptance_criteria ?? "");
      setDor(normalizeChecklist(task.dor_checklist));
      setDod(normalizeChecklist(task.dod_checklist));
      setBlockedReason(task.blocked_reason ?? "");
      setSprintId(task.sprint_id ?? "none");
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [task]);

  React.useEffect(() => {
    if (!FEATURE_AGILE_PHASE_2) return;
    let cancelled = false;
    (async () => {
      try {
        const [sprintList, deps] = await Promise.all([
          listSprints(task.task_project_id),
          listTaskDependencies(task.id),
        ]);
        if (cancelled) return;
        setSprints(sprintList);
        setDependencies(deps);
      } catch (err) {
        if (!cancelled) {
          setError(getErrorMessage(err, "Không tải được dữ liệu Phase 2"));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [task.id, task.task_project_id]);

  if (!FEATURE_AGILE_PHASE_2) {
    return null;
  }

  const handleSave = async () => {
    setError("");
    setInfo("");
    let parsedStoryPoints: number | null = null;
    if (storyPoints.trim() !== "") {
      if (!/^\d+$/.test(storyPoints.trim())) {
        setError("Điểm ước lượng phải là số nguyên không âm");
        return;
      }
      parsedStoryPoints = Number.parseInt(storyPoints.trim(), 10);
      if (!Number.isFinite(parsedStoryPoints) || parsedStoryPoints < 0) {
        setError("Điểm ước lượng phải là số nguyên không âm");
        return;
      }
    }
    setSaving(true);
    try {
      const updated = await updateTaskSemantics(task.id, {
        task_type: taskType === "none" ? null : taskType,
        estimate: estimate === "none" ? null : estimate,
        story_points: parsedStoryPoints,
        acceptance_criteria:
          acceptanceCriteria.trim() === "" ? null : acceptanceCriteria.trim(),
        dor_checklist: serializeChecklist(dor),
        dod_checklist: serializeChecklist(dod),
        blocked_reason:
          blockedReason.trim() === "" ? null : blockedReason.trim(),
        sprint_id: sprintId === "none" ? null : sprintId,
        version: task.version,
      });
      onTaskUpdated(updated);
      setInfo("Đã lưu cấu hình Agile");
    } catch (err) {
      setError(getErrorMessage(err, "Lưu cấu hình Agile thất bại"));
    } finally {
      setSaving(false);
    }
  };

  const handleAddDependency = async () => {
    setError("");
    const target = newDepId.trim();
    if (target === "") {
      setError("Nhập mã công việc cần phụ thuộc");
      return;
    }
    if (target === task.id) {
      setError("Một công việc không thể phụ thuộc vào chính nó");
      return;
    }
    try {
      const created = await addTaskDependency(task.id, target);
      setDependencies((prev) => [...prev, created]);
      setNewDepId("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = (err.data as { detail?: { code?: string } } | null)?.detail;
        if (detail?.code === "BLOCKED_CYCLE") {
          setError("Phát hiện vòng lặp phụ thuộc");
          return;
        }
        if (detail?.code === "DUPLICATE_DEPENDENCY") {
          setError("Phụ thuộc đã tồn tại");
          return;
        }
      }
      setError(getErrorMessage(err, "Không thêm được phụ thuộc"));
    }
  };

  const handleRemoveDependency = async (toTaskId: string) => {
    setError("");
    try {
      await removeTaskDependency(task.id, toTaskId);
      setDependencies((prev) => prev.filter((d) => d.to_task_id !== toTaskId));
    } catch (err) {
      setError(getErrorMessage(err, "Không gỡ được phụ thuộc"));
    }
  };

  const activeSprints = sprints.filter(
    (s) => s.status === "active" || s.status === "planned" || s.id === task.sprint_id,
  );

  return (
    <section
      className="flex flex-col gap-4 rounded-xl border border-border bg-card/40 p-4"
      data-testid="task-semantics-panel"
    >
      <header>
        <h3 className="text-base font-semibold tracking-tight text-foreground">
          Cấu hình Agile
        </h3>
        <p className="text-xs text-muted-foreground">
          Quản lý loại công việc, ước lượng, tiêu chí sẵn sàng / hoàn thành,
          Sprint và phụ thuộc.
        </p>
      </header>

      {task.blocked_reason && (
        <div
          className="rounded-lg border border-amber-300/70 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-400/40 dark:bg-amber-950/30 dark:text-amber-100"
          role="status"
          data-testid="task-blocked-banner"
        >
          <p className="font-medium">Đang bị chặn</p>
          <p className="text-xs">
            Lý do bị chặn: {task.blocked_reason}
            {task.blocked_at && (
              <span className="ml-1 opacity-80">
                · {formatTaskDateTime(task.blocked_at)}
              </span>
            )}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="task-type-select">Loại công việc</Label>
          <Select
            value={taskType}
            onValueChange={(value) => {
              if (value) setTaskType(value as TaskType | "none");
            }}
          >
            <SelectTrigger
              id="task-type-select"
              data-testid="task-type-select"
              className="w-full bg-background"
            >
              <SelectValue placeholder="Chọn loại công việc" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">— Chưa chọn —</SelectItem>
              {(Object.keys(TASK_TYPE_LABELS) as TaskType[]).map((key) => (
                <SelectItem key={key} value={key}>
                  {TASK_TYPE_LABELS[key]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="task-estimate-select">Ước lượng</Label>
          <Select
            value={estimate}
            onValueChange={(value) => {
              if (value) setEstimate(value as EstimateSize | "none");
            }}
          >
            <SelectTrigger
              id="task-estimate-select"
              data-testid="task-estimate-select"
              className="w-full bg-background"
            >
              <SelectValue placeholder="Chọn ước lượng" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">— Chưa ước lượng —</SelectItem>
              {(Object.keys(ESTIMATE_LABELS) as EstimateSize[]).map((key) => (
                <SelectItem key={key} value={key}>
                  {ESTIMATE_LABELS[key]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="task-story-points-input">Điểm ước lượng</Label>
          <Input
            id="task-story-points-input"
            data-testid="task-story-points-input"
            type="number"
            inputMode="numeric"
            min={0}
            step={1}
            placeholder="Ví dụ: 3"
            value={storyPoints}
            onChange={(event) => setStoryPoints(event.target.value)}
            className="bg-background"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="task-sprint-select">Sprint</Label>
          <Select
            value={sprintId}
            onValueChange={(value) => {
              if (value) setSprintId(value);
            }}
          >
            <SelectTrigger
              id="task-sprint-select"
              data-testid="task-sprint-select"
              className="w-full bg-background"
            >
              <SelectValue placeholder="Chọn Sprint" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">— Không thuộc Sprint nào —</SelectItem>
              {activeSprints.map((sprint) => (
                <SelectItem key={sprint.id} value={sprint.id}>
                  {sprint.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="task-acceptance-input">Tiêu chí chấp nhận</Label>
        <Textarea
          id="task-acceptance-input"
          data-testid="task-acceptance-input"
          value={acceptanceCriteria}
          onChange={(event) => setAcceptanceCriteria(event.target.value)}
          placeholder="Liệt kê các tiêu chí nghiệm thu, mỗi tiêu chí trên một dòng."
          rows={3}
          className="bg-background"
        />
      </div>

      <ChecklistEditor
        label="Tiêu chí sẵn sàng"
        testId="task-dor-checklist"
        items={dor}
        onChange={setDor}
        placeholder="Mục Definition of Ready"
      />

      <ChecklistEditor
        label="Tiêu chí hoàn thành"
        testId="task-dod-checklist"
        items={dod}
        onChange={setDod}
        placeholder="Mục Definition of Done"
      />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="task-blocked-input">Lý do bị chặn</Label>
        <Textarea
          id="task-blocked-input"
          data-testid="task-blocked-input"
          value={blockedReason}
          onChange={(event) => setBlockedReason(event.target.value)}
          placeholder="Để trống nếu công việc không bị chặn."
          rows={2}
          className="bg-background"
        />
        <p className="text-xs text-muted-foreground">
          Khi điền lý do, công việc được đánh dấu “Đang bị chặn”. Xóa nội dung
          để gỡ trạng thái chặn.
        </p>
      </div>

      <DependencyEditor
        dependencies={dependencies}
        newDepId={newDepId}
        onNewDepIdChange={setNewDepId}
        onAdd={handleAddDependency}
        onRemove={handleRemoveDependency}
      />

      {error && (
        <p
          className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
          data-testid="task-semantics-error"
        >
          {error}
        </p>
      )}
      {info && (
        <p
          className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-100"
          role="status"
          data-testid="task-semantics-info"
        >
          {info}
        </p>
      )}

      <div className="flex justify-end">
        <Button
          data-testid="task-semantics-save-btn"
          disabled={saving}
          onClick={handleSave}
          className="bg-primary text-primary-foreground hover:bg-primary/90"
        >
          {saving ? "Đang lưu…" : "Lưu cấu hình Agile"}
        </Button>
      </div>
    </section>
  );
}

type ChecklistEditorProps = {
  label: string;
  testId: string;
  items: ChecklistItem[];
  placeholder: string;
  onChange: (items: ChecklistItem[]) => void;
};

function ChecklistEditor({
  label,
  testId,
  items,
  placeholder,
  onChange,
}: ChecklistEditorProps) {
  const [draft, setDraft] = React.useState("");

  const addItem = () => {
    const value = draft.trim();
    if (value === "") return;
    onChange([
      ...items,
      { id: `c-${Date.now()}-${items.length}`, label: value, done: false },
    ]);
    setDraft("");
  };

  const toggle = (id: string) => {
    onChange(items.map((it) => (it.id === id ? { ...it, done: !it.done } : it)));
  };

  const remove = (id: string) => {
    onChange(items.filter((it) => it.id !== id));
  };

  return (
    <div className="flex flex-col gap-2" data-testid={testId}>
      <Label>{label}</Label>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">Chưa có mục nào.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5"
            >
              <input
                type="checkbox"
                checked={item.done}
                onChange={() => toggle(item.id)}
                className="h-4 w-4 accent-primary"
                aria-label={`Đánh dấu hoàn thành: ${item.label}`}
              />
              <span
                className={`flex-1 text-sm ${item.done ? "line-through opacity-60" : ""}`}
              >
                {item.label}
              </span>
              <button
                type="button"
                onClick={() => remove(item.id)}
                className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                aria-label={`Xóa mục: ${item.label}`}
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-center gap-2">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addItem();
            }
          }}
          placeholder={placeholder}
          className="bg-background"
        />
        <Button type="button" variant="outline" onClick={addItem}>
          Thêm mục
        </Button>
      </div>
    </div>
  );
}

type DependencyEditorProps = {
  dependencies: TaskDependency[];
  newDepId: string;
  onNewDepIdChange: (value: string) => void;
  onAdd: () => void;
  onRemove: (toTaskId: string) => void;
};

function DependencyEditor({
  dependencies,
  newDepId,
  onNewDepIdChange,
  onAdd,
  onRemove,
}: DependencyEditorProps) {
  return (
    <div className="flex flex-col gap-2" data-testid="task-dependencies">
      <Label>Phụ thuộc</Label>
      {dependencies.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Công việc này chưa phụ thuộc vào công việc nào.
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {dependencies.map((dep) => (
            <li
              key={dep.id}
              className="flex items-center justify-between gap-2 rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            >
              <span className="truncate font-mono text-xs">{dep.to_task_id}</span>
              <button
                type="button"
                onClick={() => onRemove(dep.to_task_id)}
                className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                aria-label={`Gỡ phụ thuộc tới ${dep.to_task_id}`}
                data-testid={`task-dependency-remove-${dep.to_task_id}`}
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-center gap-2">
        <Input
          value={newDepId}
          onChange={(event) => onNewDepIdChange(event.target.value)}
          placeholder="Mã công việc bị phụ thuộc (UUID)"
          data-testid="task-dependency-input"
          className="bg-background font-mono text-xs"
        />
        <Button
          type="button"
          variant="outline"
          onClick={onAdd}
          data-testid="task-dependency-add-btn"
        >
          Thêm phụ thuộc
        </Button>
      </div>
    </div>
  );
}
