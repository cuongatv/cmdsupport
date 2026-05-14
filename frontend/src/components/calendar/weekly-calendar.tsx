"use client";

/**
 * Weekly calendar grid — pure presentational Mon..Sun week view.
 *
 * The host page owns data loading, scope, and write actions. This component
 * only renders a positioned grid of task + habit events, the optional
 * "now" indicator, and forwards click events upward.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  CalendarEvent,
  CalendarHabitEvent,
  CalendarTaskEvent,
  HabitOccurrenceStatus,
  TaskPriority,
} from "@/lib/habit-types";
import { cn } from "@/lib/utils";

const HOUR_START = 6; // 06:00
const HOUR_END = 22; // 22:00 (exclusive bottom edge — last visible hour row is 21..22)
const HOUR_COUNT = HOUR_END - HOUR_START;
const HOUR_PX = 56; // height of one hour row in px

const PRIORITY_LABELS: Record<TaskPriority, string> = {
  none: "Không",
  low: "Thấp",
  medium: "TB",
  high: "Cao",
  urgent: "Khẩn",
};

const PRIORITY_BADGE_CLASSES: Record<TaskPriority, string> = {
  none: "bg-secondary text-muted-foreground",
  low: "bg-emerald-100 text-emerald-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-800",
  urgent: "bg-red-100 text-red-800",
};

const WEEKDAY_LABELS_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"];
const WEEKDAY_LABELS_SHORT_VI = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

const DAY_FORMATTER = new Intl.DateTimeFormat("vi-VN", {
  day: "numeric",
  month: "numeric",
});

/**
 * Add `days` to the start-of-day-local `base` date and return a new Date.
 * Avoids the daylight-saving traps from mutating the original.
 */
function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

/** Parse "YYYY-MM-DD" as a local-noon Date so day arithmetic isn't TZ-shifted. */
function parseWeekStart(weekStartIso: string): Date {
  const [y, m, d] = weekStartIso.split("-").map((v) => Number.parseInt(v, 10));
  return new Date(y, (m ?? 1) - 1, d ?? 1, 12, 0, 0, 0);
}

function isSameLocalDate(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** ISO timestamp (UTC) → local Date. */
function parseIsoLocal(iso: string): Date {
  return new Date(iso);
}

/** Minutes past midnight (local) for a Date. */
function minutesFromMidnight(date: Date): number {
  return date.getHours() * 60 + date.getMinutes();
}

/** Fractional pixel offset for a given minute count past midnight. */
function minutesToPx(mins: number): number {
  const offset = mins - HOUR_START * 60;
  return (offset / 60) * HOUR_PX;
}

function formatHourLabel(h: number): string {
  return `${String(h).padStart(2, "0")}:00`;
}

export function formatWeekRange(weekStart: Date): string {
  const end = addDays(weekStart, 6);
  const startStr = DAY_FORMATTER.format(weekStart);
  const endStr = DAY_FORMATTER.format(end);
  const year = weekStart.getFullYear() === end.getFullYear()
    ? end.getFullYear()
    : `${weekStart.getFullYear()}–${end.getFullYear()}`;
  return `${startStr} – ${endStr} ${year}`;
}

type PositionedEvent = {
  event: CalendarEvent;
  dayIndex: number; // 0..6
  topPx: number;
  heightPx: number;
};

function eventStart(ev: CalendarEvent): Date {
  return ev.event_type === "task"
    ? parseIsoLocal(ev.scheduled_start_at)
    : parseIsoLocal(ev.start);
}

function eventEnd(ev: CalendarEvent): Date {
  return ev.event_type === "task"
    ? parseIsoLocal(ev.scheduled_end_at)
    : parseIsoLocal(ev.end);
}

function positionEvents(events: CalendarEvent[], weekStart: Date): PositionedEvent[] {
  const out: PositionedEvent[] = [];
  for (const ev of events) {
    const startDate = eventStart(ev);
    const endDate = eventEnd(ev);
    const dayIndex = Math.floor(
      (new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate()).getTime() -
        new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate()).getTime()) /
        (1000 * 60 * 60 * 24),
    );
    if (dayIndex < 0 || dayIndex > 6) continue;

    const startMins = minutesFromMidnight(startDate);
    const endMins = Math.max(minutesFromMidnight(endDate), startMins + 15);

    // Clamp inside the visible window so very-early or very-late events still
    // surface as a thin bar at the top or bottom edge instead of vanishing.
    const visibleStart = Math.max(startMins, HOUR_START * 60);
    const visibleEnd = Math.min(endMins, HOUR_END * 60);
    if (visibleEnd <= visibleStart) continue;

    const topPx = minutesToPx(visibleStart);
    const heightPx = Math.max(24, minutesToPx(visibleEnd) - topPx);

    out.push({ event: ev, dayIndex, topPx, heightPx });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export type WeeklyCalendarProps = {
  weekStart: string; // "YYYY-MM-DD" (Monday)
  events: CalendarEvent[];
  loading: boolean;
  onTaskClick: (event: CalendarTaskEvent) => void;
  onHabitClick: (event: CalendarHabitEvent) => void;
  /**
   * If provided, the habit identified by (habitId + occurrenceDate) is
   * rendered in an "active" state with its popover slot reserved. Wiring is
   * fully driven by the parent; the calendar just dims the rest and shows a
   * focus ring on the target.
   */
  activeHabitKey?: string | null;
  popoverContent?: React.ReactNode;
};

export function WeeklyCalendar({
  weekStart,
  events,
  loading,
  onTaskClick,
  onHabitClick,
  activeHabitKey,
  popoverContent,
}: WeeklyCalendarProps) {
  const weekStartDate = useMemo(() => parseWeekStart(weekStart), [weekStart]);
  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStartDate, i)),
    [weekStartDate],
  );
  const positioned = useMemo(
    () => positionEvents(events, weekStartDate),
    [events, weekStartDate],
  );

  // Today + current time indicator — recompute on a 60s interval so the line
  // creeps without forcing the parent to re-render.
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const todayIndex = useMemo(() => {
    const i = days.findIndex((d) => isSameLocalDate(d, now));
    return i; // -1 if not in this week
  }, [days, now]);

  // Scroll the "now" line into view on first mount (but only when we're
  // looking at the current week).
  const gridRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (todayIndex < 0) return;
    const mins = minutesFromMidnight(now);
    if (mins < HOUR_START * 60 || mins > HOUR_END * 60) return;
    const top = minutesToPx(mins) - HOUR_PX * 2;
    const id = window.setTimeout(() => {
      gridRef.current?.scrollTo({ top: Math.max(top, 0), behavior: "auto" });
    }, 0);
    return () => window.clearTimeout(id);
  }, [todayIndex, now]);

  return (
    <>
      {/* Mobile (base..md): stacked day list. Showing seven 64px-wide columns
          on a 360px phone is impossible — gracefully degrade to a single
          scrollable column where each day is a card with its own event list. */}
      <div className="md:hidden">
        <MobileWeekList
          weekStart={weekStart}
          events={events}
          loading={loading}
          onTaskClick={onTaskClick}
          onHabitClick={onHabitClick}
          activeHabitKey={activeHabitKey}
          popoverContent={popoverContent}
        />
      </div>

      {/* Desktop (md+): full 7-column hour grid. */}
      <div className="hidden md:block rounded-xl border border-border bg-card shadow-sahara overflow-hidden">
      {/* Header row with weekdays */}
      <div className="grid grid-cols-[64px_repeat(7,minmax(0,1fr))] border-b border-border bg-secondary/30">
        <div className="border-r border-border" />
        {days.map((day, idx) => {
          const isToday = todayIndex === idx;
          return (
            <div
              key={idx}
              className={cn(
                "flex flex-col items-center justify-center py-2.5 text-center border-r border-border last:border-r-0",
                isToday && "bg-primary/10",
              )}
            >
              <span
                className={cn(
                  "text-[11px] font-semibold uppercase tracking-wider",
                  isToday ? "text-primary" : "text-muted-foreground",
                )}
              >
                {WEEKDAY_LABELS_SHORT_VI[idx]}
              </span>
              <span
                className={cn(
                  "text-base font-semibold tabular-nums",
                  isToday ? "text-primary" : "text-foreground",
                )}
                aria-label={WEEKDAY_LABELS_VI[idx]}
              >
                {DAY_FORMATTER.format(day)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Scrollable grid body */}
      <div
        ref={gridRef}
        className="relative max-h-[640px] overflow-y-auto"
        aria-busy={loading}
      >
        {/* Loading overlay — non-blocking; events render under it once loaded */}
        {loading && (
          <div className="absolute inset-0 z-30 flex items-start justify-center bg-card/70 backdrop-blur-[1px] pt-12">
            <span className="material-symbols-outlined text-3xl text-muted-foreground/60 animate-spin">
              progress_activity
            </span>
          </div>
        )}

        <div
          className="grid grid-cols-[64px_repeat(7,minmax(0,1fr))] relative"
          style={{ height: HOUR_COUNT * HOUR_PX }}
        >
          {/* Hour gutter */}
          <div className="border-r border-border bg-secondary/20">
            {Array.from({ length: HOUR_COUNT }, (_, i) => (
              <div
                key={i}
                className="relative text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70 tabular-nums"
                style={{ height: HOUR_PX }}
              >
                <span className="absolute -top-1.5 right-1.5">
                  {formatHourLabel(HOUR_START + i)}
                </span>
              </div>
            ))}
          </div>

          {/* Day columns */}
          {days.map((_day, idx) => {
            const isToday = todayIndex === idx;
            const dayEvents = positioned.filter((p) => p.dayIndex === idx);
            return (
              <div
                key={idx}
                className={cn(
                  "relative border-r border-border last:border-r-0",
                  isToday && "bg-primary/[0.03]",
                )}
              >
                {/* Hour grid lines */}
                {Array.from({ length: HOUR_COUNT }, (_, h) => (
                  <div
                    key={h}
                    className="border-b border-border/60"
                    style={{ height: HOUR_PX }}
                  />
                ))}

                {/* Now indicator on today column */}
                {isToday && (() => {
                  const mins = minutesFromMidnight(now);
                  if (mins < HOUR_START * 60 || mins > HOUR_END * 60) return null;
                  const top = minutesToPx(mins);
                  return (
                    <div
                      className="absolute left-0 right-0 z-20 pointer-events-none"
                      style={{ top }}
                      aria-hidden="true"
                    >
                      <div className="relative">
                        <span className="absolute -left-1 -top-[5px] block h-2.5 w-2.5 rounded-full bg-red-500 shadow" />
                        <div className="h-[2px] bg-red-500/90" />
                      </div>
                    </div>
                  );
                })()}

                {/* Events */}
                {dayEvents.map((pe) => (
                  <CalendarEventCard
                    key={
                      pe.event.event_type === "task"
                        ? `task-${pe.event.task_id}-${pe.topPx}`
                        : `habit-${pe.event.habit_id}-${pe.topPx}`
                    }
                    positioned={pe}
                    activeHabitKey={activeHabitKey}
                    popoverContent={popoverContent}
                    onTaskClick={onTaskClick}
                    onHabitClick={onHabitClick}
                  />
                ))}
              </div>
            );
          })}
        </div>

        {/* Empty state — only when we're done loading and have nothing to show */}
        {!loading && events.length === 0 && (
          <div className="absolute inset-x-0 top-1/3 flex flex-col items-center text-center px-6 pointer-events-none">
            <span
              className="material-symbols-outlined text-4xl text-muted-foreground/40"
              style={{ fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 32" }}
            >
              event_busy
            </span>
            <p className="mt-2 text-sm font-medium text-foreground">
              Tuần này không có công việc hay thói quen nào
            </p>
            <p className="text-xs text-muted-foreground max-w-xs">
              Lịch sẽ hiển thị các công việc đã lên lịch và thói quen cá nhân khi chúng được tạo.
            </p>
          </div>
        )}
      </div>
    </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Mobile fallback: stacked day-list view
//
// At base width (below `md:`), the 7-column hour grid is impractical:
// 64px gutter + 7 × ~40px = ~344px BEFORE any event content, on a 360px
// viewport. Instead, render a vertical stack of day cards. Each day card
// has a header (weekday + date + "Hôm nay" pill if applicable) and a list
// of events sorted by start time. Empty days collapse to a single
// "Không có gì" placeholder so the user can still see the day at a glance.
// ---------------------------------------------------------------------------

function MobileWeekList({
  weekStart,
  events,
  loading,
  onTaskClick,
  onHabitClick,
  activeHabitKey,
  popoverContent,
}: WeeklyCalendarProps) {
  const weekStartDate = useMemo(() => parseWeekStart(weekStart), [weekStart]);
  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStartDate, i)),
    [weekStartDate],
  );
  const now = useMemo(() => new Date(), []);
  const todayIndex = useMemo(
    () => days.findIndex((d) => isSameLocalDate(d, now)),
    [days, now],
  );

  // Bucket events by day index (0..6, Mon..Sun). Events outside the week
  // are silently dropped — mirrors the desktop `positionEvents` behaviour.
  const eventsByDay = useMemo(() => {
    const buckets: CalendarEvent[][] = Array.from({ length: 7 }, () => []);
    for (const ev of events) {
      const start = eventStart(ev);
      const idx = Math.floor(
        (new Date(start.getFullYear(), start.getMonth(), start.getDate()).getTime() -
          new Date(
            weekStartDate.getFullYear(),
            weekStartDate.getMonth(),
            weekStartDate.getDate(),
          ).getTime()) /
          (1000 * 60 * 60 * 24),
      );
      if (idx >= 0 && idx <= 6) buckets[idx].push(ev);
    }
    for (const bucket of buckets) {
      bucket.sort((a, b) => eventStart(a).getTime() - eventStart(b).getTime());
    }
    return buckets;
  }, [events, weekStartDate]);

  if (loading) {
    return <MobileWeekListSkeleton />;
  }

  if (events.length === 0) {
    return (
      <div
        className="rounded-xl border border-border bg-card shadow-sahara py-12 px-4 flex flex-col items-center text-center"
        role="status"
      >
        <span
          className="material-symbols-outlined text-4xl text-muted-foreground/40"
          style={{ fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 32" }}
        >
          event_busy
        </span>
        <p className="mt-2 text-sm font-medium text-foreground">
          Tuần này không có công việc hay thói quen nào
        </p>
        <p className="text-xs text-muted-foreground max-w-xs">
          Lịch sẽ hiển thị các công việc đã lên lịch và thói quen cá nhân khi chúng được tạo.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {days.map((day, idx) => {
        const dayEvents = eventsByDay[idx];
        const isToday = todayIndex === idx;
        return (
          <section
            key={idx}
            className={cn(
              "rounded-xl border bg-card shadow-sahara overflow-hidden",
              isToday ? "border-primary/40" : "border-border",
            )}
          >
            <header
              className={cn(
                "px-4 py-3 flex items-center gap-3 border-b border-border",
                isToday ? "bg-primary/10" : "bg-secondary/30",
              )}
            >
              <div className="flex flex-col">
                <span
                  className={cn(
                    "text-[11px] font-semibold uppercase tracking-wider",
                    isToday ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  {WEEKDAY_LABELS_VI[idx]}
                </span>
                <span
                  className={cn(
                    "text-base font-semibold tabular-nums",
                    isToday ? "text-primary" : "text-foreground",
                  )}
                  aria-label={WEEKDAY_LABELS_VI[idx]}
                >
                  {DAY_FORMATTER.format(day)}
                </span>
              </div>
              {isToday && (
                <span className="inline-flex items-center gap-1 rounded-full bg-primary text-primary-foreground px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider">
                  Hôm nay
                </span>
              )}
              <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                {dayEvents.length === 0
                  ? "Trống"
                  : `${dayEvents.length} sự kiện`}
              </span>
            </header>
            {dayEvents.length === 0 ? (
              <div className="px-4 py-6 text-xs text-muted-foreground/70 italic text-center">
                Không có công việc hay thói quen
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {dayEvents.map((ev) =>
                  ev.event_type === "task" ? (
                    <MobileTaskRow
                      key={`task-${ev.task_id}-${ev.scheduled_start_at}`}
                      event={ev}
                      onClick={() => onTaskClick(ev)}
                    />
                  ) : (
                    <MobileHabitRow
                      key={`habit-${ev.habit_id}-${ev.start}`}
                      event={ev}
                      activeHabitKey={activeHabitKey}
                      popoverContent={popoverContent}
                      onClick={() => onHabitClick(ev)}
                    />
                  ),
                )}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

function MobileTaskRow({
  event,
  onClick,
}: {
  event: CalendarTaskEvent;
  onClick: () => void;
}) {
  const priorityClass =
    PRIORITY_BADGE_CLASSES[event.priority] ?? PRIORITY_BADGE_CLASSES.none;
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="group w-full flex items-center gap-3 px-4 py-3 min-h-[56px] text-left transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:bg-primary/5"
      >
        <span
          className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary shrink-0"
          aria-hidden="true"
        >
          <span
            className="material-symbols-outlined text-[18px]"
            style={{ fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
          >
            task_alt
          </span>
        </span>
        <div className="flex-1 min-w-0 flex flex-col gap-0.5">
          <span className="text-sm font-medium text-foreground truncate">
            {event.title}
          </span>
          <span className="text-[11px] text-muted-foreground tabular-nums">
            {formatTimeRange(event.scheduled_start_at, event.scheduled_end_at)}
          </span>
        </div>
        <span
          className={cn(
            "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium shrink-0",
            priorityClass,
          )}
        >
          {PRIORITY_LABELS[event.priority] ?? event.priority}
        </span>
        <span className="material-symbols-outlined text-base text-muted-foreground/40 group-hover:text-muted-foreground shrink-0">
          chevron_right
        </span>
      </button>
    </li>
  );
}

function MobileHabitRow({
  event,
  activeHabitKey,
  popoverContent,
  onClick,
}: {
  event: CalendarHabitEvent;
  activeHabitKey?: string | null;
  popoverContent?: React.ReactNode;
  onClick: () => void;
}) {
  const stateTone = stateTones(event.state);
  const occurrenceDate = parseIsoLocal(event.start).toISOString().slice(0, 10);
  const key = `${event.habit_id}:${occurrenceDate}`;
  const isActive = activeHabitKey === key;
  return (
    <li className="relative">
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "group w-full flex items-center gap-3 px-4 py-3 min-h-[56px] text-left transition-colors hover:bg-secondary/40 focus-visible:outline-none focus-visible:bg-secondary/40",
          isActive && "bg-secondary/60",
        )}
      >
        <span
          className={cn(
            "inline-flex h-9 w-9 items-center justify-center rounded-md border-2 border-dashed shrink-0",
            stateTone.surface,
            stateTone.border,
          )}
          aria-hidden="true"
        >
          <span
            className={cn("material-symbols-outlined text-[18px]", stateTone.icon)}
            style={{ fontVariationSettings: "'FILL' 0, 'wght' 500, 'GRAD' 0, 'opsz' 20" }}
          >
            {stateTone.iconName}
          </span>
        </span>
        <div className="flex-1 min-w-0 flex flex-col gap-0.5">
          <span className={cn("text-sm font-medium truncate", stateTone.title)}>
            {event.title}
          </span>
          <span className={cn("text-[11px] tabular-nums", stateTone.subdued)}>
            {formatTimeRange(event.start, event.end)}
            {event.shift_reason ? ` · ${event.shift_reason}` : ""}
          </span>
        </div>
        <span className="material-symbols-outlined text-base text-muted-foreground/40 group-hover:text-muted-foreground shrink-0">
          chevron_right
        </span>
      </button>
      {isActive && popoverContent}
    </li>
  );
}

/**
 * Skeleton for the mobile week list. Renders 3 placeholder day cards
 * with header bars and ~2 event rows each so the layout doesn't flash
 * a spinner-only screen during the initial load.
 */
function MobileWeekListSkeleton() {
  return (
    <div
      className="flex flex-col gap-3"
      aria-busy="true"
      aria-label="Đang tải lịch tuần"
    >
      {[0, 1, 2].map((i) => (
        <section
          key={i}
          className="rounded-xl border border-border bg-card shadow-sahara overflow-hidden animate-pulse"
        >
          <header className="px-4 py-3 flex items-center gap-3 bg-secondary/30 border-b border-border">
            <div className="flex flex-col gap-1.5">
              <div className="h-2.5 w-12 rounded bg-muted" />
              <div className="h-4 w-10 rounded bg-muted" />
            </div>
            <div className="ml-auto h-3 w-16 rounded bg-muted" />
          </header>
          <ul className="divide-y divide-border">
            {[0, 1].map((j) => (
              <li key={j} className="flex items-center gap-3 px-4 py-3">
                <div className="h-9 w-9 rounded-md bg-muted shrink-0" />
                <div className="flex-1 flex flex-col gap-1.5 min-w-0">
                  <div className="h-3.5 w-3/4 rounded bg-muted" />
                  <div className="h-2.5 w-1/3 rounded bg-muted" />
                </div>
                <div className="h-5 w-10 rounded bg-muted shrink-0" />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Event cards
// ---------------------------------------------------------------------------

function CalendarEventCard({
  positioned,
  activeHabitKey,
  popoverContent,
  onTaskClick,
  onHabitClick,
}: {
  positioned: PositionedEvent;
  activeHabitKey?: string | null;
  popoverContent?: React.ReactNode;
  onTaskClick: (event: CalendarTaskEvent) => void;
  onHabitClick: (event: CalendarHabitEvent) => void;
}) {
  const { event, topPx, heightPx } = positioned;

  if (event.event_type === "task") {
    return (
      <TaskEventCard
        event={event}
        topPx={topPx}
        heightPx={heightPx}
        onClick={() => onTaskClick(event)}
      />
    );
  }

  const occurrenceDate = parseIsoLocal(event.start)
    .toISOString()
    .slice(0, 10);
  const key = `${event.habit_id}:${occurrenceDate}`;
  const isActive = activeHabitKey === key;

  return (
    <HabitEventCard
      event={event}
      topPx={topPx}
      heightPx={heightPx}
      isActive={isActive}
      onClick={() => onHabitClick(event)}
      popoverContent={isActive ? popoverContent : undefined}
    />
  );
}

function TaskEventCard({
  event,
  topPx,
  heightPx,
  onClick,
}: {
  event: CalendarTaskEvent;
  topPx: number;
  heightPx: number;
  onClick: () => void;
}) {
  const priorityClass = PRIORITY_BADGE_CLASSES[event.priority] ?? PRIORITY_BADGE_CLASSES.none;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group absolute left-1 right-1 z-10 flex flex-col gap-1 overflow-hidden rounded-md border border-primary/30 bg-primary/10 text-left px-2 py-1.5 transition-all",
        "hover:border-primary/60 hover:bg-primary/15 hover:shadow-sm",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
      )}
      style={{ top: topPx, height: heightPx }}
      title={event.title}
    >
      <div className="flex items-center gap-1.5 min-w-0">
        <span
          className="material-symbols-outlined text-[14px] text-primary shrink-0"
          style={{ fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 18" }}
          aria-hidden="true"
        >
          task_alt
        </span>
        <span className="text-xs font-semibold text-primary truncate">{event.title}</span>
      </div>
      {heightPx >= 48 && (
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium",
              priorityClass,
            )}
          >
            {PRIORITY_LABELS[event.priority] ?? event.priority}
          </span>
          <span className="text-[10px] text-primary/70 tabular-nums truncate">
            {formatTimeRange(event.scheduled_start_at, event.scheduled_end_at)}
          </span>
        </div>
      )}
    </button>
  );
}

function HabitEventCard({
  event,
  topPx,
  heightPx,
  isActive,
  onClick,
  popoverContent,
}: {
  event: CalendarHabitEvent;
  topPx: number;
  heightPx: number;
  isActive: boolean;
  onClick: () => void;
  popoverContent?: React.ReactNode;
}) {
  const stateTone = stateTones(event.state);
  return (
    <div
      className="absolute left-1 right-1 z-10"
      style={{ top: topPx, height: heightPx }}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "group relative flex h-full w-full flex-col gap-1 overflow-hidden rounded-md border-2 border-dashed text-left px-2 py-1.5 transition-all",
          stateTone.surface,
          stateTone.border,
          "hover:shadow-sm",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
          isActive && "ring-2 ring-primary/60",
        )}
        title={event.title}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className={cn(
              "material-symbols-outlined text-[14px] shrink-0",
              stateTone.icon,
            )}
            style={{ fontVariationSettings: "'FILL' 0, 'wght' 500, 'GRAD' 0, 'opsz' 18" }}
            aria-hidden="true"
          >
            {stateTone.iconName}
          </span>
          <span className={cn("text-xs font-semibold truncate", stateTone.title)}>
            {event.title}
          </span>
        </div>

        {heightPx >= 44 && (
          <div className={cn("text-[10px] tabular-nums truncate", stateTone.subdued)}>
            {formatTimeRange(event.start, event.end)}
          </div>
        )}

        {event.shift_reason && heightPx >= 58 && (
          <div className="flex items-center gap-1 text-[10px] text-amber-700">
            <span
              className="material-symbols-outlined text-[12px]"
              aria-hidden="true"
            >
              shift_lock
            </span>
            <span className="truncate">{event.shift_reason}</span>
          </div>
        )}
      </button>

      {isActive && popoverContent}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TIME_FORMATTER = new Intl.DateTimeFormat("vi-VN", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function formatTimeRange(startIso: string, endIso: string): string {
  return `${TIME_FORMATTER.format(parseIsoLocal(startIso))}–${TIME_FORMATTER.format(parseIsoLocal(endIso))}`;
}

function stateTones(state: HabitOccurrenceStatus | null): {
  surface: string;
  border: string;
  title: string;
  subdued: string;
  icon: string;
  iconName: string;
} {
  switch (state) {
    case "completed":
      return {
        surface: "bg-emerald-50",
        border: "border-emerald-300",
        title: "text-emerald-800 line-through decoration-emerald-700/40",
        subdued: "text-emerald-700/80",
        icon: "text-emerald-600",
        iconName: "task_alt",
      };
    case "skipped":
      return {
        surface: "bg-muted",
        border: "border-muted-foreground/30",
        title: "text-muted-foreground line-through",
        subdued: "text-muted-foreground/70",
        icon: "text-muted-foreground",
        iconName: "block",
      };
    case "shifted":
      return {
        surface: "bg-amber-50",
        border: "border-amber-300",
        title: "text-amber-900",
        subdued: "text-amber-700/80",
        icon: "text-amber-600",
        iconName: "schedule",
      };
    default:
      return {
        surface: "bg-secondary/40",
        border: "border-secondary-foreground/30",
        title: "text-foreground",
        subdued: "text-muted-foreground",
        icon: "text-muted-foreground",
        iconName: "self_improvement",
      };
  }
}
