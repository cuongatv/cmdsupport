"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import {
  getCalendarWeek,
  updatePersonalTask,
  upsertOccurrence,
} from "@/lib/habit-api";
import {
  getTask,
  getTaskProject,
  listEligibleAssignees,
  listTaskLabels,
  listTaskStates,
  listTasks,
} from "@/lib/task-api";
import type {
  CalendarEvent,
  CalendarHabitEvent,
  CalendarTaskEvent,
  CalendarWeekResponse,
  HabitOccurrenceStatus,
  UnitDashboardAggregate,
} from "@/lib/habit-types";
import type {
  EligibleAssignee,
  Task,
  TaskLabel,
  TaskProject,
  TaskState,
} from "@/lib/task-types";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { TaskDetailPanel } from "@/components/tasks/task-detail-panel";
import { WeeklyCalendar, formatWeekRange } from "@/components/calendar/weekly-calendar";
import {
  bumpAfterHabitMutation,
  bumpDashboardVersion,
  bumpUnitsVersion,
  useCalendarVersion,
  useFocusBump,
} from "@/lib/me-sync";
import { cn } from "@/lib/utils";

/**
 * Return ISO YYYY-MM-DD for the Monday on or before `date` (local time).
 *
 * Date.getDay() returns 0..6 starting Sunday — convert to a Mon=0..Sun=6
 * index so Sunday subtracts 6 days instead of advancing by one. Matches the
 * Python `date.weekday()` convention used everywhere in the backend.
 */
function startOfWeekMonday(date: Date): string {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const sundayBased = d.getDay();
  const monBased = (sundayBased + 6) % 7; // Mon=0..Sun=6
  d.setDate(d.getDate() - monBased);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function parseWeekStart(weekStartIso: string): Date {
  const [y, m, d] = weekStartIso.split("-").map((v) => Number.parseInt(v, 10));
  return new Date(y, (m ?? 1) - 1, d ?? 1, 12, 0, 0, 0);
}

function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

type Scope =
  | { kind: "personal" }
  | { kind: "department"; deptId: string };

const PERSONAL_SCOPE: Scope = { kind: "personal" };

function scopeKey(scope: Scope): string {
  return scope.kind === "personal" ? "personal" : `dept:${scope.deptId}`;
}

export default function MeCalendarPage() {
  // Cross-surface sync: re-fetch on calendar bumps + tab refocus. The
  // popover's occurrence upsert calls `bumpAfterHabitMutation()` below,
  // which bumps calendar (this page picks it up) + habits + dashboard.
  const calendarVersion = useCalendarVersion();
  useFocusBump();

  const [scope, setScope] = useState<Scope>(PERSONAL_SCOPE);
  const [weekStart, setWeekStart] = useState<string>(() =>
    startOfWeekMonday(new Date()),
  );

  const [units, setUnits] = useState<UnitDashboardAggregate[]>([]);
  const [unitsLoading, setUnitsLoading] = useState(true);

  const [data, setData] = useState<CalendarWeekResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Active popover key — `${habit_id}:${YYYY-MM-DD}`. Single-popover-at-a-time
  // is plenty: this isn't a multi-select interface.
  const [activeHabitKey, setActiveHabitKey] = useState<string | null>(null);
  const [activeHabit, setActiveHabit] = useState<CalendarHabitEvent | null>(null);
  const [popoverPending, setPopoverPending] = useState<HabitOccurrenceStatus | "undo" | null>(null);
  const [popoverError, setPopoverError] = useState("");

  // Drag-drop state — owned here so the calendar stays presentational.
  // `pendingMove` carries the optimistic position; `savingTaskId` flags the
  // in-flight PATCH so the card can be dimmed; `moveError` surfaces failures
  // in the existing red error band (same row as the load error).
  const [pendingMove, setPendingMove] = useState<{
    taskId: string;
    newStart: Date;
    newEnd: Date;
  } | null>(null);
  const [savingTaskId, setSavingTaskId] = useState<string | null>(null);
  const [savingHabitId, setSavingHabitId] = useState<string | null>(null);
  const [moveError, setMoveError] = useState("");

  // Task detail panel — opens when the user clicks a task card on the
  // calendar. Mirrors the /admin/tasks list flow so the click feels
  // identical: same modal, same edit/comment/attachment surface. Detail
  // context (project, states, labels, eligible assignees, parent
  // candidates) is lazy-loaded per task because /me/calendar can show
  // tasks from many projects (cá nhân + đơn vị + workspace).
  const { hasPermission } = useAuth();
  const canEdit =
    hasPermission("task:edit:own_dept") || hasPermission("task:edit:all");
  const canDelete =
    hasPermission("task:delete:own_dept") || hasPermission("task:delete:all");

  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailProject, setDetailProject] = useState<TaskProject | null>(null);
  const [detailStates, setDetailStates] = useState<TaskState[]>([]);
  const [detailLabels, setDetailLabels] = useState<TaskLabel[]>([]);
  const [detailAssignees, setDetailAssignees] = useState<EligibleAssignee[]>(
    [],
  );
  const [detailParentCandidates, setDetailParentCandidates] = useState<Task[]>(
    [],
  );

  // ESC closes the habit popover. Project-wide convention.
  useEffect(() => {
    if (!activeHabitKey) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setActiveHabitKey(null);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeHabitKey]);

  // ---------- units list (scope toggle source) ----------
  useEffect(() => {
    let cancelled = false;
    const id = window.setTimeout(() => {
      setUnitsLoading(true);
      void (async () => {
        try {
          const res = await api<UnitDashboardAggregate[]>("/api/me/units");
          if (cancelled) return;
          setUnits(res);
        } catch {
          if (cancelled) return;
          setUnits([]);
        } finally {
          if (!cancelled) setUnitsLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, []);

  // ---------- week data ----------
  const fetchKey = useMemo(
    () => `${weekStart}|${scopeKey(scope)}`,
    [weekStart, scope],
  );

  const [reloadTick, setReloadTick] = useState(0);
  const reload = useCallback(() => {
    // Increments a counter that's part of the data effect's dep list, so
    // the same week+scope combo can be re-fetched after a write.
    setReloadTick((t) => t + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const id = window.setTimeout(() => {
      setLoading(true);
      setError("");
      void (async () => {
        try {
          const res = await getCalendarWeek(
            weekStart,
            scope.kind,
            scope.kind === "department" ? scope.deptId : undefined,
          );
          if (cancelled) return;
          setData(res);
        } catch (err) {
          if (cancelled) return;
          setData(null);
          setError(getErrorMessage(err, "Không tải được lịch tuần"));
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [fetchKey, reloadTick, scope, weekStart, calendarVersion]);

  // ---------- nav handlers ----------
  const goPrev = useCallback(() => {
    const prev = addDays(parseWeekStart(weekStart), -7);
    setWeekStart(startOfWeekMonday(prev));
    setActiveHabitKey(null);
    setActiveHabit(null);
  }, [weekStart]);

  const goNext = useCallback(() => {
    const nxt = addDays(parseWeekStart(weekStart), 7);
    setWeekStart(startOfWeekMonday(nxt));
    setActiveHabitKey(null);
    setActiveHabit(null);
  }, [weekStart]);

  const goToday = useCallback(() => {
    setWeekStart(startOfWeekMonday(new Date()));
    setActiveHabitKey(null);
    setActiveHabit(null);
  }, []);

  // ---------- event handlers ----------
  // Fetch the full Task (calendar event only carries task_id + scheduling
  // metadata) and open the same TaskDetailPanel the /admin/tasks list
  // uses. Detail-context (project, states, labels, assignees, parent
  // candidates) is loaded by the effect below — same lazy-load pattern
  // /me/tasks page uses.
  const handleTaskClick = useCallback((event: CalendarTaskEvent) => {
    setDetailError("");
    void (async () => {
      try {
        const task = await getTask(event.task_id);
        setSelectedTask(task);
      } catch (err) {
        setDetailError(getErrorMessage(err, "Không tải được công việc"));
      }
    })();
  }, []);

  // Load the detail-panel context whenever a task is selected. Mirrors the
  // /me/tasks `loadDetailContext` flow exactly: each task can belong to a
  // different project, so we fetch per-task rather than relying on a
  // page-level cache.
  const loadDetailContext = useCallback(async (task: Task | null) => {
    if (task === null) {
      setDetailProject(null);
      setDetailStates([]);
      setDetailLabels([]);
      setDetailAssignees([]);
      setDetailParentCandidates([]);
      return;
    }
    const projectId = task.task_project_id;
    try {
      const project = await getTaskProject(projectId);
      const [statesData, assigneesData, labelsData, parentRes] =
        await Promise.all([
          listTaskStates(projectId).catch(() => [] as TaskState[]),
          listEligibleAssignees(projectId).catch(
            () => [] as EligibleAssignee[],
          ),
          listTaskLabels(projectId).catch(() => [] as TaskLabel[]),
          listTasks({
            task_project_id: projectId,
            page: 1,
            page_size: 100,
          }).catch(() => ({
            items: [] as Task[],
            total: 0,
            page: 1,
            page_size: 100,
            total_pages: 0,
          })),
        ]);
      setDetailProject(project);
      setDetailStates(statesData);
      setDetailAssignees(assigneesData);
      setDetailLabels(labelsData);
      setDetailParentCandidates(
        parentRes.items.filter((t) => t.parent_task_id === null),
      );
    } catch {
      setDetailProject(null);
      setDetailStates([]);
      setDetailLabels([]);
      setDetailAssignees([]);
      setDetailParentCandidates([]);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const timerId = window.setTimeout(() => {
      if (cancelled) return;
      void loadDetailContext(selectedTask);
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [selectedTask, loadDetailContext]);

  const handleDetailPanelOpenChange = useCallback((open: boolean) => {
    if (!open) {
      setSelectedTask(null);
      setDetailError("");
    }
  }, []);

  const handleHabitClick = useCallback((event: CalendarHabitEvent) => {
    const occurrenceDate = new Date(event.start).toISOString().slice(0, 10);
    const key = `${event.habit_id}:${occurrenceDate}`;
    setActiveHabit(event);
    setActiveHabitKey((prev) => (prev === key ? null : key));
    setPopoverError("");
  }, []);

  // ---------- drag-drop write action ----------
  const handleTaskMove = useCallback(
    async (taskId: string, newStart: Date) => {
      const orig = (data?.events ?? []).find(
        (ev): ev is CalendarTaskEvent =>
          ev.event_type === "task" && ev.task_id === taskId,
      );
      if (!orig) return;

      // Preserve the task's original duration on move. Backend stores
      // `due_date` as the END marker (block ends at due_date — see
      // app/routers/habits.py), so we PATCH the new end.
      const origStart = new Date(orig.scheduled_start_at);
      const origEnd = new Date(orig.scheduled_end_at);
      const duration = Math.max(
        origEnd.getTime() - origStart.getTime(),
        15 * 60 * 1000, // never collapse below 15 min
      );
      const newEnd = new Date(newStart.getTime() + duration);

      // No-op: dropped on the same slot the task already occupies.
      if (origStart.getTime() === newStart.getTime()) return;

      setPendingMove({ taskId, newStart, newEnd });
      setSavingTaskId(taskId);
      setMoveError("");

      try {
        await updatePersonalTask(taskId, { due_date: newEnd.toISOString() });
        // Cross-surface bump so dashboard buckets + unit aggregates refresh
        // on next visit, then refetch this week to pick up the new times.
        bumpDashboardVersion();
        bumpUnitsVersion();
        reload();
      } catch (err) {
        setMoveError(getErrorMessage(err, "Không cập nhật được công việc"));
      } finally {
        setPendingMove(null);
        setSavingTaskId(null);
      }
    },
    [data, reload],
  );

  // Drag a habit on the calendar → per-occurrence override for THAT day only.
  // The habit's template (preferred_time, active_days) at /me/habits stays
  // untouched; every other day still renders at the original time. Backend
  // stores the override as `actual_start` on `habit_occurrence_states` keyed
  // by (habit_id, occurrence_date) — see Rule 0 in app/routers/habits.py
  // _build_habit_events.
  //
  // To change the recurring template the user must edit the habit at /me/habits.
  const handleHabitMove = useCallback(
    async (habitId: string, newTimeHHmm: string, occurrenceDate: string) => {
      const orig = (data?.events ?? []).find(
        (ev): ev is CalendarHabitEvent =>
          ev.event_type === "habit" && ev.habit_id === habitId,
      );
      if (!orig) return;
      const origDate = new Date(orig.start);
      const origHHmm = `${String(origDate.getHours()).padStart(2, "0")}:${String(origDate.getMinutes()).padStart(2, "0")}`;
      if (origHHmm === newTimeHHmm) return;

      setSavingHabitId(habitId);
      setMoveError("");
      try {
        // Upsert per-day override. State "shifted" matches the semantics:
        // user moved this occurrence away from the template's preferred_time.
        // Existing state (completed/skipped) is overwritten — drag-after-complete
        // is rare; if it surfaces as a UX issue we'll thread the previous state
        // through here.
        await upsertOccurrence(habitId, occurrenceDate, {
          state: "shifted",
          actual_start: `${newTimeHHmm}:00`,
        });
        bumpAfterHabitMutation();
        reload();
      } catch (err) {
        setMoveError(getErrorMessage(err, "Không đổi giờ thói quen"));
      } finally {
        setSavingHabitId(null);
      }
    },
    [data, reload],
  );

  // ---------- popover write actions ----------
  const handleOccurrenceWrite = useCallback(
    async (state: HabitOccurrenceStatus, label: HabitOccurrenceStatus | "undo") => {
      if (!activeHabit) return;
      const occurrenceDate = new Date(activeHabit.start).toISOString().slice(0, 10);
      setPopoverPending(label);
      setPopoverError("");
      try {
        await upsertOccurrence(activeHabit.habit_id, occurrenceDate, { state });
        // Optimistic-ish: refetch the week to surface the new state, but
        // close the popover immediately so the user gets feedback. Also
        // broadcast to the habits + dashboard surfaces so other /me pages
        // re-fetch on next visit.
        setActiveHabitKey(null);
        setActiveHabit(null);
        bumpAfterHabitMutation();
        reload();
      } catch (err) {
        setPopoverError(getErrorMessage(err, "Không cập nhật được"));
      } finally {
        setPopoverPending(null);
      }
    },
    [activeHabit, reload],
  );

  // ---------- derived ----------
  const events: CalendarEvent[] = data?.events ?? [];
  const rangeLabel = formatWeekRange(parseWeekStart(weekStart));
  const isCurrentWeek = weekStart === startOfWeekMonday(new Date());

  return (
    <>
      <PageHeader
        title="Lịch tuần"
        description="Tổng hợp công việc đã lên lịch và thói quen cá nhân theo tuần. Bấm vào sự kiện để xem chi tiết hoặc cập nhật trạng thái."
      />

      {/* Toolbar: scope + nav */}
      <div className="rounded-xl border border-border bg-card shadow-sahara p-3 sm:p-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        {/* Scope chips */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mr-2">
            Phạm vi
          </span>
          <ScopeChip
            label="Cá nhân"
            icon="person"
            active={scope.kind === "personal"}
            onClick={() => {
              setScope(PERSONAL_SCOPE);
              setActiveHabitKey(null);
            }}
          />
          {unitsLoading ? (
            <span className="inline-flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground/60">
              <span className="material-symbols-outlined text-[14px] animate-spin">
                progress_activity
              </span>
              Đang tải đơn vị…
            </span>
          ) : (
            units.map((unit) => (
              <ScopeChip
                key={unit.unit_id}
                label={unit.unit_name}
                icon="domain"
                active={scope.kind === "department" && scope.deptId === unit.unit_id}
                onClick={() => {
                  setScope({ kind: "department", deptId: unit.unit_id });
                  setActiveHabitKey(null);
                }}
              />
            ))
          )}
        </div>

        {/* Week nav */}
        <div className="flex flex-wrap items-center gap-2 self-end lg:self-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={goPrev}
            aria-label="Tuần trước"
            className="min-h-[40px] min-w-[40px] sm:min-h-8 sm:min-w-0 px-2"
          >
            <span className="material-symbols-outlined text-base">chevron_left</span>
          </Button>
          <Button
            variant={isCurrentWeek ? "secondary" : "outline"}
            size="sm"
            onClick={goToday}
            className="min-h-[40px] sm:min-h-8"
          >
            <span className="material-symbols-outlined text-sm">today</span>
            Hôm nay
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={goNext}
            aria-label="Tuần sau"
            className="min-h-[40px] min-w-[40px] sm:min-h-8 sm:min-w-0 px-2"
          >
            <span className="material-symbols-outlined text-base">chevron_right</span>
          </Button>
          <span className="w-full sm:w-auto sm:ml-1 sm:min-w-[140px] sm:text-right text-sm font-semibold text-foreground tabular-nums">
            {rangeLabel}
          </span>
        </div>
      </div>

      {/* Error band with retry — surfaces both the week-fetch error and any
          drag-drop PATCH failure. The retry button only re-fetches the week,
          which is also the right escape hatch after a failed move. */}
      {(error || moveError) && (
        <div
          className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3"
          role="alert"
        >
          <span className="flex items-start gap-2 flex-1">
            <span className="material-symbols-outlined text-base mt-0.5 shrink-0">
              error_outline
            </span>
            <span>{error || moveError}</span>
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setMoveError("");
              reload();
            }}
            className="min-h-[40px] sm:min-h-7 self-start sm:self-auto px-2 border-destructive/30 text-destructive hover:bg-destructive/10"
          >
            <span className="material-symbols-outlined text-sm">refresh</span>
            Thử lại
          </Button>
        </div>
      )}

      {/* Calendar grid */}
      <WeeklyCalendar
        weekStart={weekStart}
        events={events}
        loading={loading}
        onTaskClick={handleTaskClick}
        onHabitClick={handleHabitClick}
        onTaskMove={handleTaskMove}
        onHabitMove={handleHabitMove}
        pendingMove={pendingMove}
        savingTaskId={savingTaskId}
        savingHabitId={savingHabitId}
        activeHabitKey={activeHabitKey}
        popoverContent={
          activeHabit ? (
            <HabitPopover
              event={activeHabit}
              pending={popoverPending}
              error={popoverError}
              onComplete={() => handleOccurrenceWrite("completed", "completed")}
              onSkip={() => handleOccurrenceWrite("skipped", "skipped")}
              onUndo={() => handleOccurrenceWrite("shifted", "undo")}
              onClose={() => {
                setActiveHabitKey(null);
                setActiveHabit(null);
                setPopoverError("");
              }}
            />
          ) : null
        }
      />

      {detailError && (
        <div
          className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center gap-2"
          role="alert"
        >
          <span className="material-symbols-outlined text-base">error</span>
          {detailError}
        </div>
      )}

      {/* Task detail modal — same component the unit task list uses, so the
          click experience matches across surfaces. The panel handles its
          own edit/comment/attachment UI; we just feed it task + project
          context and refresh the calendar grid when something mutates. */}
      {selectedTask && detailProject && (
        <TaskDetailPanel
          key={selectedTask.id}
          open={selectedTask !== null}
          onOpenChange={handleDetailPanelOpenChange}
          task={selectedTask}
          project={detailProject}
          states={detailStates}
          labels={detailLabels}
          eligibleAssignees={detailAssignees}
          parentCandidates={detailParentCandidates}
          canEdit={canEdit}
          canDelete={canDelete}
          onChanged={() => {
            // A task edit can shift due_date / state / assignee — any of
            // which may move the task on the calendar grid. Refetch the
            // week + reload the detail context so the panel itself
            // reflects the new values too.
            reload();
            void loadDetailContext(selectedTask);
          }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ScopeChip({
  label,
  icon,
  active,
  onClick,
}: {
  label: string;
  icon: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-2 sm:py-1 min-h-[40px] sm:min-h-7 text-xs font-medium transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-background text-foreground hover:bg-secondary/50",
      )}
      aria-pressed={active}
    >
      <span
        className="material-symbols-outlined text-[14px]"
        style={{ fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 18" }}
        aria-hidden="true"
      >
        {icon}
      </span>
      <span className="truncate max-w-[180px]">{label}</span>
    </button>
  );
}

function HabitPopover({
  event,
  pending,
  error,
  onComplete,
  onSkip,
  onUndo,
  onClose,
}: {
  event: CalendarHabitEvent;
  pending: HabitOccurrenceStatus | "undo" | null;
  error: string;
  onComplete: () => void;
  onSkip: () => void;
  onUndo: () => void;
  onClose: () => void;
}) {
  const isCompleted = event.state === "completed";
  const isSkipped = event.state === "skipped";

  return (
    <div
      // Centered below the habit card. `absolute` lives in the parent div in
      // weekly-calendar; this layer just sets dimensions + z-index.
      className="absolute left-1/2 top-full z-40 mt-1.5 w-[220px] -translate-x-1/2 rounded-lg border border-border bg-card p-2 shadow-lg ring-1 ring-black/[0.04]"
      role="dialog"
      aria-label="Cập nhật trạng thái thói quen"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="px-1.5 pb-1.5 border-b border-border">
        <p className="text-xs font-semibold text-foreground truncate">
          {event.title}
        </p>
        {event.shift_reason && (
          <p className="text-[10px] text-amber-700 mt-0.5 truncate">
            {event.shift_reason}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-0.5 mt-1">
        <PopoverButton
          icon="done"
          label="Hoàn thành"
          tone="emerald"
          disabled={isCompleted || pending !== null}
          loading={pending === "completed"}
          onClick={onComplete}
        />
        <PopoverButton
          icon="block"
          label="Bỏ qua"
          tone="muted"
          disabled={isSkipped || pending !== null}
          loading={pending === "skipped"}
          onClick={onSkip}
        />
        <PopoverButton
          icon="undo"
          label="Hoàn tác"
          tone="amber"
          disabled={pending !== null || (event.state === null)}
          loading={pending === "undo"}
          onClick={onUndo}
        />
      </div>

      {error && (
        <p className="mt-1.5 px-1.5 text-[10px] text-destructive">{error}</p>
      )}

      <button
        type="button"
        onClick={onClose}
        className="absolute right-1 top-1 rounded p-0.5 text-muted-foreground/60 hover:bg-secondary hover:text-foreground transition-colors"
        aria-label="Đóng"
      >
        <span className="material-symbols-outlined text-[14px]">close</span>
      </button>
    </div>
  );
}

function PopoverButton({
  icon,
  label,
  tone,
  disabled,
  loading,
  onClick,
}: {
  icon: string;
  label: string;
  tone: "emerald" | "muted" | "amber";
  disabled: boolean;
  loading: boolean;
  onClick: () => void;
}) {
  const TONES: Record<typeof tone, string> = {
    emerald: "text-emerald-700 hover:bg-emerald-50",
    muted: "text-muted-foreground hover:bg-secondary",
    amber: "text-amber-700 hover:bg-amber-50",
  };
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 rounded px-2 py-2.5 sm:py-1.5 min-h-[40px] sm:min-h-7 text-xs text-left transition-colors",
        TONES[tone],
        disabled && "opacity-40 cursor-not-allowed hover:bg-transparent",
      )}
    >
      <span
        className="material-symbols-outlined text-[16px]"
        style={{ fontVariationSettings: "'FILL' 0, 'wght' 500, 'GRAD' 0, 'opsz' 18" }}
        aria-hidden="true"
      >
        {loading ? "progress_activity" : icon}
      </span>
      <span className={cn(loading && "animate-pulse")}>{label}</span>
    </button>
  );
}
