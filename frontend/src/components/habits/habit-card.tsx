"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TASK_PRIORITY_LABELS } from "@/components/tasks/task-list-filters";
import type {
  HabitOccurrenceStatus,
  HabitRead,
  TaskPriority,
} from "@/lib/habit-types";
import { cn } from "@/lib/utils";

// 0 = Mon … 6 = Sun. Matches Python's `date.weekday()` and the
// `personal_habits.active_days` JSONB schema.
const WEEKDAY_LABELS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const WEEKDAY_TITLES = [
  "Thứ Hai",
  "Thứ Ba",
  "Thứ Tư",
  "Thứ Năm",
  "Thứ Sáu",
  "Thứ Bảy",
  "Chủ Nhật",
];

const PRIORITY_CLASSES: Record<TaskPriority, string> = {
  none: "border-border text-muted-foreground bg-background",
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  high: "bg-orange-50 text-orange-700 border-orange-200",
  urgent: "bg-red-50 text-red-700 border-red-200",
};

/** "HH:MM:SS" → "HH:MM" for display. */
function trimTimeForDisplay(value: string): string {
  return value.length >= 5 ? value.slice(0, 5) : value;
}

export type HabitCardProps = {
  habit: HabitRead;
  /**
   * The optimistic state for the *current local day*. `undefined` means
   * the user hasn't acted in this session; the card shows neutral buttons.
   * `null` is the explicit "no occurrence yet" state.
   */
  todayState: HabitOccurrenceStatus | null | undefined;
  /** Which toggle is currently writing (or null if idle). */
  pending: HabitOccurrenceStatus | "undo" | null;
  onEdit: (habit: HabitRead) => void;
  onArchive: (habit: HabitRead) => void;
  onToggle: (
    habit: HabitRead,
    state: HabitOccurrenceStatus,
    label: HabitOccurrenceStatus | "undo",
  ) => void;
};

export function HabitCard({
  habit,
  todayState,
  pending,
  onEdit,
  onArchive,
  onToggle,
}: HabitCardProps) {
  const archived = !habit.is_active;
  const priorityClass =
    PRIORITY_CLASSES[habit.priority] ?? PRIORITY_CLASSES.none;
  const priorityLabel =
    TASK_PRIORITY_LABELS[habit.priority] ?? habit.priority;
  const activeDays = [...habit.active_days].sort((a, b) => a - b);

  const isCompleted = todayState === "completed";
  const isSkipped = todayState === "skipped";
  // "undo" maps to the backend `shifted` state — neutral re-start.
  const hasTouchedToday =
    todayState === "completed" ||
    todayState === "skipped" ||
    todayState === "shifted";

  return (
    <article
      className={cn(
        "rounded-xl border bg-card shadow-sahara p-4 flex flex-col gap-3 transition-opacity",
        archived ? "border-dashed border-border/70 opacity-65" : "border-border",
      )}
    >
      {/* Top row: title + priority + archive label + actions */}
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0 flex flex-col gap-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-foreground truncate">
              {habit.title}
            </h3>
            <Badge variant="outline" className={cn("text-[11px]", priorityClass)}>
              {priorityLabel}
            </Badge>
            {archived && (
              <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                <span className="material-symbols-outlined text-[12px]">
                  archive
                </span>
                Đã lưu trữ
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground tabular-nums">
            <span className="inline-flex items-center gap-1">
              <span className="material-symbols-outlined text-[14px]">
                schedule
              </span>
              {trimTimeForDisplay(habit.preferred_time)}
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="material-symbols-outlined text-[14px]">
                hourglass_empty
              </span>
              {habit.duration_minutes} phút
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => onEdit(habit)}
            aria-label="Chỉnh sửa thói quen"
            title="Chỉnh sửa"
            className="min-h-[40px] min-w-[40px] sm:min-h-7 sm:min-w-7"
          >
            <span className="material-symbols-outlined text-[18px]">edit</span>
          </Button>
          {!archived && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => onArchive(habit)}
              aria-label="Lưu trữ thói quen"
              title="Lưu trữ"
              className="min-h-[40px] min-w-[40px] sm:min-h-7 sm:min-w-7 text-muted-foreground hover:text-red-600"
            >
              <span className="material-symbols-outlined text-[18px]">
                archive
              </span>
            </Button>
          )}
        </div>
      </div>

      {/* Weekday chips */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {WEEKDAY_LABELS.map((label, idx) => {
          const active = activeDays.includes(idx);
          return (
            <span
              key={idx}
              title={WEEKDAY_TITLES[idx]}
              className={cn(
                "inline-flex h-6 min-w-[1.75rem] items-center justify-center rounded-md border px-1.5 text-[11px] font-semibold",
                active
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border bg-background text-muted-foreground/60",
              )}
            >
              {label}
            </span>
          );
        })}
      </div>

      {/* Today's quick toggle — hidden for archived habits */}
      {!archived && (
        <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Hôm nay
          </span>
          <div className="flex items-center gap-1">
            <ToggleButton
              icon="done"
              label="Hoàn thành"
              tone="emerald"
              active={isCompleted}
              disabled={isCompleted || pending !== null}
              loading={pending === "completed"}
              onClick={() => onToggle(habit, "completed", "completed")}
            />
            <ToggleButton
              icon="block"
              label="Bỏ qua"
              tone="amber"
              active={isSkipped}
              disabled={isSkipped || pending !== null}
              loading={pending === "skipped"}
              onClick={() => onToggle(habit, "skipped", "skipped")}
            />
            <ToggleButton
              icon="undo"
              label="Hoàn tác"
              tone="slate"
              active={false}
              // "Hoàn tác" is only meaningful when the user has marked
              // something for today — disabled otherwise to avoid useless writes.
              disabled={!hasTouchedToday || pending !== null}
              loading={pending === "undo"}
              onClick={() => onToggle(habit, "shifted", "undo")}
            />
          </div>
        </div>
      )}
    </article>
  );
}

type ToggleButtonProps = {
  icon: string;
  label: string;
  tone: "emerald" | "amber" | "slate";
  active: boolean;
  disabled: boolean;
  loading: boolean;
  onClick: () => void;
};

function ToggleButton({
  icon,
  label,
  tone,
  active,
  disabled,
  loading,
  onClick,
}: ToggleButtonProps) {
  const TONES: Record<ToggleButtonProps["tone"], { active: string; idle: string }> =
    {
      emerald: {
        active: "border-emerald-300 bg-emerald-50 text-emerald-700",
        idle: "border-border bg-background text-muted-foreground hover:border-emerald-200 hover:text-emerald-700",
      },
      amber: {
        active: "border-amber-300 bg-amber-50 text-amber-700",
        idle: "border-border bg-background text-muted-foreground hover:border-amber-200 hover:text-amber-700",
      },
      slate: {
        active: "border-slate-300 bg-slate-50 text-slate-700",
        idle: "border-border bg-background text-muted-foreground hover:border-slate-300 hover:text-slate-700",
      },
    };
  const tones = TONES[tone];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={cn(
        // Tap target: 40px on mobile (meets the 40px accessibility floor),
        // back to 28px on sm+ so the row stays compact on desktop.
        "inline-flex h-10 w-10 sm:h-7 sm:w-7 items-center justify-center rounded-md border transition-colors",
        active ? tones.active : tones.idle,
        disabled && "opacity-50 cursor-not-allowed hover:border-border hover:text-muted-foreground",
      )}
    >
      <span
        className="material-symbols-outlined text-[16px]"
        style={{
          fontVariationSettings: active
            ? "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 18"
            : "'FILL' 0, 'wght' 500, 'GRAD' 0, 'opsz' 18",
        }}
        aria-hidden="true"
      >
        {loading ? "progress_activity" : icon}
      </span>
    </button>
  );
}
