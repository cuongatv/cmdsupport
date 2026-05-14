"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getCalendarWeek, upsertOccurrence } from "@/lib/habit-api";
import type {
  CalendarEvent,
  CalendarHabitEvent,
  CalendarTaskEvent,
  CalendarWeekResponse,
  HabitOccurrenceStatus,
  UnitDashboardAggregate,
} from "@/lib/habit-types";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { WeeklyCalendar, formatWeekRange } from "@/components/calendar/weekly-calendar";
import {
  bumpAfterHabitMutation,
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
  const router = useRouter();
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
  const handleTaskClick = useCallback(
    (event: CalendarTaskEvent) => {
      router.push(`/admin/tasks/${event.task_id}`);
    },
    [router],
  );

  const handleHabitClick = useCallback((event: CalendarHabitEvent) => {
    const occurrenceDate = new Date(event.start).toISOString().slice(0, 10);
    const key = `${event.habit_id}:${occurrenceDate}`;
    setActiveHabit(event);
    setActiveHabitKey((prev) => (prev === key ? null : key));
    setPopoverError("");
  }, []);

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

      {/* Error band with retry */}
      {error && (
        <div
          className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3"
          role="alert"
        >
          <span className="flex items-start gap-2 flex-1">
            <span className="material-symbols-outlined text-base mt-0.5 shrink-0">
              error_outline
            </span>
            <span>{error}</span>
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={reload}
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
