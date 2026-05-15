"use client";

/**
 * Weekly calendar grid — pure presentational Mon..Sun week view.
 *
 * The host page owns data loading, scope, and write actions. This component
 * only renders a positioned grid of task + habit events, the optional
 * "now" indicator, and forwards click events upward.
 *
 * Drag-and-drop: task events on the desktop grid are draggable to any other
 * day×slot. Drop snaps to 30-minute slots. The host page owns the optimistic
 * `pendingMove` state and the PATCH call; this component only emits
 * `onTaskMove(taskId, newStart)` and visually applies `pendingMove` while
 * the server is being updated.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  DndContext,
  type DragEndEvent,
  type DragStartEvent,
  PointerSensor,
  useDndMonitor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
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

/** A "slot" is either a single event OR a stack of overlapping events.
 *  Stacks may mix tasks and habits — when a habit and task land on the same
 *  vertical pixel range, both go into one dropdown so the user only sees a
 *  single chip in that slot. Inside the dropdown each row renders per its
 *  own event_type (task → drag-to-reschedule, habit → status popover).
 *
 *  Overlap rule: two events `a` and `b` overlap when both occupy the same
 *  vertical pixel range — i.e. `a.topPx < b.topPx + b.heightPx` AND
 *  `a.topPx + a.heightPx > b.topPx`. We keep groups simple and order-stable:
 *  first event becomes the group anchor; subsequent events that overlap the
 *  anchor's [top, top+height) interval join the same group. This is O(n²) per
 *  day but each day rarely has >20 events, so the cost is negligible. */
type EventSlot =
  | { kind: "single"; positioned: PositionedEvent }
  | {
      kind: "stack";
      anchor: PositionedEvent;
      members: PositionedEvent[]; // length >= 2; members[0] === anchor
    };

function groupOverlappingTaskSlots(dayEvents: PositionedEvent[]): EventSlot[] {
  const slots: EventSlot[] = [];
  const taken = new Set<number>();

  for (let i = 0; i < dayEvents.length; i++) {
    if (taken.has(i)) continue;
    const a = dayEvents[i];
    const aTop = a.topPx;
    const aBottom = a.topPx + a.heightPx;
    const members: PositionedEvent[] = [a];
    for (let j = i + 1; j < dayEvents.length; j++) {
      if (taken.has(j)) continue;
      const b = dayEvents[j];
      const bTop = b.topPx;
      const bBottom = b.topPx + b.heightPx;
      if (aTop < bBottom && aBottom > bTop) {
        members.push(b);
        taken.add(j);
      }
    }
    taken.add(i);
    if (members.length === 1) {
      slots.push({ kind: "single", positioned: a });
    } else {
      slots.push({ kind: "stack", anchor: a, members });
    }
  }
  return slots;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export type PendingTaskMove = {
  taskId: string;
  newStart: Date;
  newEnd: Date;
};

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
  /**
   * Drag-drop: emitted when a task event is dropped on a different day×slot.
   * Host should PATCH the task's `due_date` and reload. Mobile does NOT call
   * this (mobile is read-only).
   */
  onTaskMove?: (taskId: string, newStart: Date) => void;
  /**
   * Drag-drop for habits: emitted when a habit event is dropped on a
   * different time slot. The day component is IGNORED here — drag is a
   * per-occurrence override for the day the habit currently sits on, NOT a
   * cross-day move. Host should upsert the (habit_id, occurrenceDate)
   * occurrence row with the new actual_start. `newTimeHHmm` is "HH:mm"
   * Hanoi-local; `occurrenceDate` is "YYYY-MM-DD" of the dragged event's
   * existing day.
   */
  onHabitMove?: (
    habitId: string,
    newTimeHHmm: string,
    occurrenceDate: string,
  ) => void;
  /**
   * Optimistic overlay: while a task is being moved, the host pre-renders
   * the new position by setting this. The calendar substitutes the task's
   * scheduled times before laying it out.
   */
  pendingMove?: PendingTaskMove | null;
  /** Task currently being PATCHed — dimmed in-place to signal "saving". */
  savingTaskId?: string | null;
  /** Habit currently being PATCHed — dimmed in-place to signal "saving". */
  savingHabitId?: string | null;
};

export function WeeklyCalendar({
  weekStart,
  events,
  loading,
  onTaskClick,
  onHabitClick,
  activeHabitKey,
  popoverContent,
  onTaskMove,
  onHabitMove,
  pendingMove,
  savingTaskId,
  savingHabitId,
}: WeeklyCalendarProps) {
  const weekStartDate = useMemo(() => parseWeekStart(weekStart), [weekStart]);
  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStartDate, i)),
    [weekStartDate],
  );

  // Apply optimistic pending move BEFORE positioning so the dragged task
  // visually snaps to its new spot the instant the user releases the mouse.
  // The host clears `pendingMove` once the server-confirmed reload arrives.
  const overlaidEvents = useMemo<CalendarEvent[]>(() => {
    if (!pendingMove) return events;
    return events.map((ev) =>
      ev.event_type === "task" && ev.task_id === pendingMove.taskId
        ? {
            ...ev,
            scheduled_start_at: pendingMove.newStart.toISOString(),
            scheduled_end_at: pendingMove.newEnd.toISOString(),
          }
        : ev,
    );
  }, [events, pendingMove]);

  const positioned = useMemo(
    () => positionEvents(overlaidEvents, weekStartDate),
    [overlaidEvents, weekStartDate],
  );

  // PointerSensor with a 6px activation distance so a click on the card
  // (to open task detail) doesn't accidentally trigger a drag.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const handleDragEnd = (e: DragEndEvent) => {
    const { active, over, delta, activatorEvent } = e;
    if (!over) return;
    const overData = over.data.current as { dayIndex?: number } | undefined;
    const activeData = active.data.current as
      | {
          taskId?: string;
          habitId?: string;
          // For habit drags only — the YYYY-MM-DD of the occurrence the user
          // grabbed. Carried in active data so handleDragEnd doesn't have to
          // scan `events` (and accidentally land on the wrong weekday since
          // every weekday of the same habit shares habit_id).
          occurrenceDate?: string;
          originalTopPx?: number;
          // `fromStack=true` means the drag originated from a TaskStackCard
          // dropdown row, NOT from a positioned card on the grid. Stack rows
          // have no fixed top/height in the column — we compute the new slot
          // from the pointer's final viewport Y instead of `originalTopPx +
          // delta.y`.
          fromStack?: boolean;
        }
      | undefined;
    if (
      !overData ||
      typeof overData.dayIndex !== "number" ||
      !activeData
    ) {
      return;
    }
    const isHabit = typeof activeData.habitId === "string";
    const isTask = typeof activeData.taskId === "string";
    if (!isHabit && !isTask) return;
    if (isHabit && !onHabitMove) return;
    if (isTask && !onTaskMove) return;

    // Two ways to compute the drop position:
    //   1. Card dragged from grid → originalTopPx + delta.y (its origin lived
    //      at known pixel offset within the column).
    //   2. Row dragged from stack dropdown → use pointer coords. The dropdown
    //      sits anywhere on screen; we have the activator event (the original
    //      pointerdown) plus dnd-kit's delta and the droppable's bounding rect.
    let newTopPx: number;
    if (activeData.fromStack === true) {
      const startY =
        activatorEvent instanceof MouseEvent ||
        activatorEvent instanceof PointerEvent
          ? activatorEvent.clientY
          : 0;
      const finalY = startY + delta.y;
      // over.rect.top is the day column's top in viewport coords. Convert to
      // an offset within the column.
      newTopPx = finalY - over.rect.top;
    } else {
      if (typeof activeData.originalTopPx !== "number") return;
      newTopPx = activeData.originalTopPx + delta.y;
    }

    // Snap to nearest 30-min slot from the column's top.
    const slotIndex = Math.max(
      0,
      Math.min(
        Math.round(newTopPx / (HOUR_PX / 2)),
        (HOUR_END - HOUR_START) * 2 - 1,
      ),
    );
    const newStartMinutes = HOUR_START * 60 + slotIndex * 30;
    const newHour = Math.floor(newStartMinutes / 60);
    const newMinute = newStartMinutes % 60;

    if (isHabit && activeData.habitId && activeData.occurrenceDate) {
      // Habits: per-occurrence override. Day of drop is IGNORED — drag only
      // shifts the time on the day the event currently lives on. Cross-day
      // moves don't have a meaning for habits (the template controls which
      // days the habit runs). occurrenceDate comes straight from the
      // dragged element's data — DO NOT scan `events` by habit_id, that
      // would return the first weekday and silently move the wrong day.
      const occurrenceDate = activeData.occurrenceDate;
      const orig = events.find(
        (ev): ev is CalendarHabitEvent => {
          if (ev.event_type !== "habit") return false;
          if (ev.habit_id !== activeData.habitId) return false;
          const d = new Date(ev.start);
          const dKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
          return dKey === occurrenceDate;
        },
      );
      if (orig) {
        const origDate = new Date(orig.start);
        if (
          origDate.getHours() === newHour &&
          origDate.getMinutes() === newMinute
        ) {
          return;
        }
      }
      const hhmm = `${String(newHour).padStart(2, "0")}:${String(newMinute).padStart(2, "0")}`;
      onHabitMove?.(activeData.habitId, hhmm, occurrenceDate);
      return;
    }

    // Task path
    if (!activeData.taskId) return;
    const dayDate = addDays(weekStartDate, overData.dayIndex);
    const newStart = new Date(
      dayDate.getFullYear(),
      dayDate.getMonth(),
      dayDate.getDate(),
    );
    newStart.setHours(newHour);
    newStart.setMinutes(newMinute);
    newStart.setSeconds(0);
    newStart.setMilliseconds(0);

    // No-op if the user dropped on the exact same slot.
    const orig = events.find(
      (ev): ev is CalendarTaskEvent =>
        ev.event_type === "task" && ev.task_id === activeData.taskId,
    );
    if (orig) {
      const origStart = new Date(orig.scheduled_start_at);
      if (origStart.getTime() === newStart.getTime()) return;
    }

    onTaskMove?.(activeData.taskId, newStart);
  };

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
  // looking at the current week). gridRef is the scroll container that
  // wraps both the sticky header and the hour grid body.
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

      {/* Desktop (md+): full 7-column hour grid.
          Header + body share ONE scroll container so they always have the
          same content-box width — no scrollbar-induced column drift. The
          header uses `sticky top-0` so day labels stay visible while the
          user scrolls through the hours of the day. */}
      <div
        ref={gridRef}
        className="hidden md:block rounded-xl border border-border bg-card shadow-sahara max-h-[calc(100vh-280px)] min-h-[480px] overflow-y-auto"
        aria-busy={loading}
      >
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      {/* Header row with weekdays */}
      <div className="grid grid-cols-[64px_repeat(7,minmax(0,1fr))] border-b border-border bg-secondary/30 sticky top-0 z-20">
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

      {/* Grid body — sits inside the same scroll container as the header above. */}
      <div className="relative">
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

          {/* Day columns — one droppable per day; onDragEnd snaps to 30-min slots. */}
          {days.map((_day, idx) => {
            const isToday = todayIndex === idx;
            const dayEvents = positioned.filter((p) => p.dayIndex === idx);
            return (
              <DayDroppable
                key={idx}
                dayIndex={idx}
                isToday={isToday}
                dayEvents={dayEvents}
                now={now}
                activeHabitKey={activeHabitKey}
                popoverContent={popoverContent}
                onTaskClick={onTaskClick}
                onHabitClick={onHabitClick}
                savingTaskId={savingTaskId}
                savingHabitId={savingHabitId}
              />
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
      </DndContext>
    </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Droppable day column wrapper
// ---------------------------------------------------------------------------

function DayDroppable({
  dayIndex,
  isToday,
  dayEvents,
  now,
  activeHabitKey,
  popoverContent,
  onTaskClick,
  onHabitClick,
  savingTaskId,
  savingHabitId,
}: {
  dayIndex: number;
  isToday: boolean;
  dayEvents: PositionedEvent[];
  now: Date;
  activeHabitKey?: string | null;
  popoverContent?: React.ReactNode;
  onTaskClick: (event: CalendarTaskEvent) => void;
  onHabitClick: (event: CalendarHabitEvent) => void;
  savingTaskId?: string | null;
  savingHabitId?: string | null;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `day-${dayIndex}`,
    data: { dayIndex },
  });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "relative border-r border-border last:border-r-0 transition-colors",
        isToday && "bg-primary/[0.03]",
        isOver && "bg-primary/10 ring-2 ring-primary/40 ring-inset",
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

      {/* Events — overlapping events (tasks AND/OR habits) collapse into a
          single "+N việc trùng giờ" stack card with a popover dropdown. */}
      {groupOverlappingTaskSlots(dayEvents).map((slot) => {
        if (slot.kind === "single") {
          const pe = slot.positioned;
          return (
            <CalendarEventCard
              key={
                pe.event.event_type === "task"
                  ? `task-${pe.event.task_id}`
                  : `habit-${pe.event.habit_id}-${pe.topPx}`
              }
              positioned={pe}
              activeHabitKey={activeHabitKey}
              popoverContent={popoverContent}
              onTaskClick={onTaskClick}
              onHabitClick={onHabitClick}
              savingTaskId={savingTaskId}
              savingHabitId={savingHabitId}
            />
          );
        }
        // stack key: prefer anchor task_id, else habit_id+topPx — stable
        // across re-renders even if member order changes.
        const anchorEv = slot.anchor.event;
        const stackKey =
          anchorEv.event_type === "task"
            ? `stack-task-${anchorEv.task_id}`
            : `stack-habit-${anchorEv.habit_id}-${slot.anchor.topPx}`;
        return (
          <TaskStackCard
            key={stackKey}
            slot={slot}
            onTaskClick={onTaskClick}
            onHabitClick={onHabitClick}
            savingTaskId={savingTaskId}
            savingHabitId={savingHabitId}
          />
        );
      })}
    </div>
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

  return (
    <div className="flex flex-col gap-3">
      {events.length === 0 && (
        <div
          className="rounded-xl border border-dashed border-border bg-card/50 px-4 py-3 text-xs text-muted-foreground text-center"
          role="status"
        >
          Tuần này chưa có công việc hay thói quen. Bảng lịch theo ngày vẫn hiển thị bên dưới.
        </div>
      )}
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
  savingTaskId,
  savingHabitId,
}: {
  positioned: PositionedEvent;
  activeHabitKey?: string | null;
  popoverContent?: React.ReactNode;
  onTaskClick: (event: CalendarTaskEvent) => void;
  onHabitClick: (event: CalendarHabitEvent) => void;
  savingTaskId?: string | null;
  savingHabitId?: string | null;
}) {
  const { event, topPx, heightPx } = positioned;

  if (event.event_type === "task") {
    return (
      <TaskEventCard
        event={event}
        topPx={topPx}
        heightPx={heightPx}
        onClick={() => onTaskClick(event)}
        isSaving={savingTaskId === event.task_id}
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
      isSaving={savingHabitId === event.habit_id}
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
  isSaving,
}: {
  event: CalendarTaskEvent;
  topPx: number;
  heightPx: number;
  onClick: () => void;
  isSaving?: boolean;
}) {
  const priorityClass = PRIORITY_BADGE_CLASSES[event.priority] ?? PRIORITY_BADGE_CLASSES.none;

  // Make the task block draggable. The original top/height pixel values are
  // stashed in `data` so the parent's onDragEnd can recover the resting
  // position and snap the drop to the nearest 30-minute slot.
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: `task-${event.task_id}`,
      data: {
        taskId: event.task_id,
        originalTopPx: topPx,
        originalHeightPx: heightPx,
      },
      disabled: isSaving,
    });

  const dragTransform = CSS.Translate.toString(transform);

  return (
    <button
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      type="button"
      onClick={onClick}
      className={cn(
        "group absolute left-1 right-1 z-10 flex flex-col justify-center gap-1 overflow-hidden rounded-md border border-primary/30 bg-primary/10 text-left px-2 py-1.5 transition-all cursor-grab",
        "hover:border-primary/60 hover:bg-primary/15 hover:shadow-sm",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
        isDragging && "opacity-50 shadow-lg z-30 cursor-grabbing",
        isSaving && "opacity-60",
      )}
      style={{
        top: topPx,
        height: heightPx,
        transform: dragTransform,
      }}
      title={event.title}
    >
      <div className="flex items-center gap-1.5 min-w-0">
        <span
          className={cn(
            "material-symbols-outlined text-[14px] shrink-0",
            isSaving ? "text-primary/70 animate-spin" : "text-primary",
          )}
          style={{ fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 18" }}
          aria-hidden="true"
        >
          {isSaving ? "progress_activity" : "task_alt"}
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

/**
 * Card shown when ≥2 task events overlap the same vertical pixel range.
 * Renders a chip "+N công việc cần thực hiện"; clicking opens a small
 * dropdown listing every member task. Clicking a row in the dropdown
 * forwards to the host page's onTaskClick (router push to /admin/tasks/[id]).
 *
 * Position uses the EARLIEST start + the MAX end of the group so the card
 * spans the full overlap region. Kept dragless on purpose: drag-drop a
 * stack is ambiguous (which task moves?). Users open the dropdown, click
 * one, and drag THAT task individually after it's expanded later.
 */
function TaskStackCard({
  slot,
  onTaskClick,
  onHabitClick,
  savingTaskId,
  savingHabitId,
}: {
  slot: { kind: "stack"; anchor: PositionedEvent; members: PositionedEvent[] };
  onTaskClick: (event: CalendarTaskEvent) => void;
  onHabitClick: (event: CalendarHabitEvent) => void;
  savingTaskId?: string | null;
  savingHabitId?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [memberDragging, setMemberDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const memberDraggableIds = useMemo(() => {
    const ids = new Set<string>();
    for (const m of slot.members) {
      if (m.event.event_type === "task") ids.add(m.event.task_id);
      else ids.add(m.event.habit_id);
    }
    return ids;
  }, [slot.members]);

  // Track whether one of this stack's members is currently being dragged.
  // While that's true we:
  //   1. Keep the dropdown open (rows must stay mounted or dnd-kit drops it).
  //   2. Let the dropdown overflow visible (the dragged row's CSS transform
  //      would otherwise be clipped by the popover's max-h scroll container).
  //   3. Skip the "click outside closes me" handler — dnd-kit's PointerSensor
  //      fires mousedown events outside the row that would otherwise close
  //      the popover and unmount the row mid-gesture.
  useDndMonitor({
    onDragStart(event: DragStartEvent) {
      const data = event.active.data.current as
        | {
            taskId?: string;
            habitId?: string;
            fromStack?: boolean;
            fromHabitStack?: boolean;
          }
        | undefined;
      if (!data) return;
      const fromStackRow = data.fromStack === true || data.fromHabitStack === true;
      if (!fromStackRow) return;
      const id = data.taskId ?? data.habitId;
      if (id && memberDraggableIds.has(id)) {
        setMemberDragging(true);
      }
    },
    onDragEnd() {
      if (memberDragging) {
        setMemberDragging(false);
        setOpen(false);
      }
    },
    onDragCancel() {
      if (memberDragging) {
        setMemberDragging(false);
      }
    },
  });

  // Click outside / ESC closes the dropdown. Suspend the outside-click guard
  // while a member is being dragged (see useDndMonitor comment above).
  useEffect(() => {
    if (!open || memberDragging) return;
    const onPointer = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, memberDragging]);

  // Span the union [minTop, maxBottom] of the group.
  const topPx = Math.min(...slot.members.map((m) => m.topPx));
  const bottomPx = Math.max(...slot.members.map((m) => m.topPx + m.heightPx));
  const heightPx = Math.max(40, bottomPx - topPx);

  const count = slot.members.length;
  const hasSavingMember = slot.members.some(
    (m) =>
      m.event.event_type === "task" &&
      savingTaskId === m.event.task_id,
  );

  // Distinguish three label modes:
  //   - tasks only       → "+N việc cần thực hiện"
  //   - habits only      → "+N thói quen trùng giờ" (rare; habits don't usually
  //                        overlap each other)
  //   - tasks + habits   → "Công việc trùng giờ thói quen" (the common
  //                        cross-type case the user explicitly called out)
  const taskCount = slot.members.filter(
    (m) => m.event.event_type === "task",
  ).length;
  const habitCount = count - taskCount;
  const isMixed = taskCount > 0 && habitCount > 0;
  // Urgent habit conflict = at least one urgent habit landed in this stack.
  // Backend never auto-shifts urgent habits out of overlaps, so the stack
  // chip surfaces a red warning so the user knows this isn't a routine
  // overlap they can ignore.
  const hasUrgentHabitConflict = slot.members.some(
    (m) => m.event.event_type === "habit" && m.event.priority === "urgent",
  );
  const stackLabel = isMixed
    ? "Công việc trùng giờ thói quen"
    : taskCount > 0
      ? `+${count} việc cần thực hiện`
      : `+${count} thói quen trùng giờ`;
  const stackTitle = hasUrgentHabitConflict
    ? `${taskCount} công việc trùng giờ thói quen khẩn cấp`
    : isMixed
      ? `${taskCount} công việc + ${habitCount} thói quen trùng giờ`
      : `${count} việc trùng giờ`;

  return (
    <div
      ref={containerRef}
      className="absolute left-1 right-1 z-10"
      style={{ top: topPx, height: heightPx }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "group relative flex h-full w-full flex-col items-start justify-center gap-1 overflow-hidden rounded-md border text-left px-2 py-1.5 transition-all",
          "focus-visible:outline-none focus-visible:ring-2",
          hasUrgentHabitConflict
            ? "border-red-400 bg-red-50 hover:border-red-500 hover:bg-red-100 focus-visible:ring-red-300"
            : "border-primary/40 bg-primary/15 hover:border-primary/60 hover:bg-primary/20 focus-visible:ring-primary/40",
          "hover:shadow-sm",
          hasSavingMember && "opacity-60",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={stackTitle}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className={cn(
              "material-symbols-outlined text-[14px] shrink-0",
              hasUrgentHabitConflict ? "text-red-600" : "text-primary",
            )}
            style={{ fontVariationSettings: "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 18" }}
            aria-hidden="true"
          >
            {hasUrgentHabitConflict ? "warning" : "stacks"}
          </span>
          <span
            className={cn(
              "text-xs font-semibold truncate",
              hasUrgentHabitConflict ? "text-red-700" : "text-primary",
            )}
          >
            {stackLabel}
          </span>
        </div>
        {heightPx >= 44 && (
          <span className="text-[10px] text-primary/70 truncate">
            Bấm để xem danh sách
          </span>
        )}
      </button>

      {open && (
        <div
          className={cn(
            "absolute left-1/2 top-full z-40 mt-1.5 w-[260px] -translate-x-1/2 rounded-lg border border-border bg-card p-1 shadow-lg ring-1 ring-black/[0.04]",
            // Allow the dragged row's CSS translate to escape the popover
            // bounds and draw across the calendar grid.
            memberDragging && "overflow-visible",
          )}
          role="listbox"
          aria-label="Chọn công việc"
        >
          <div className="px-2 py-1.5 border-b border-border">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {stackTitle}
            </p>
          </div>
          <ul
            className={cn(
              "flex flex-col gap-0.5 mt-1",
              // Default scroll container; lifted while a row is being dragged
              // so the row's CSS transform can paint outside the popover.
              memberDragging
                ? "overflow-visible"
                : "max-h-[280px] overflow-y-auto",
            )}
          >
            {slot.members.map((m) => {
              const ev = m.event;
              if (ev.event_type === "task") {
                const isSaving = savingTaskId === ev.task_id;
                return (
                  <li key={`task-${ev.task_id}`}>
                    <StackRowDraggable
                      event={ev}
                      isSaving={isSaving}
                      onPick={() => {
                        setOpen(false);
                        onTaskClick(ev);
                      }}
                    />
                  </li>
                );
              }
              // habit row — draggable (kéo để đổi giờ template). The drag
              // updates `preferred_time` for the whole recurrence (Mon..Fri
              // etc.), not just this one occurrence.
              const isHabitSaving = savingHabitId === ev.habit_id;
              return (
                <li key={`habit-${ev.habit_id}-${m.topPx}`}>
                  <StackRowHabit
                    event={ev}
                    isSaving={isHabitSaving}
                    onPick={() => {
                      setOpen(false);
                      onHabitClick(ev);
                    }}
                  />
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * One row in a TaskStackCard dropdown. Acts as both a click target (open the
 * task) AND a draggable source — user can grab a row out of the dropdown and
 * drop it on any day×slot to reschedule that single task. The row's drag id
 * carries `fromStack: true` so the calendar's `handleDragEnd` knows to
 * compute the new slot from the pointer's final viewport Y rather than the
 * row's own (irrelevant) position inside the popover.
 *
 * activationConstraint distance=6px on the parent DndContext sensor still
 * applies — short clicks open the task, longer drag motions trigger move.
 */
function StackRowDraggable({
  event,
  isSaving,
  onPick,
}: {
  event: CalendarTaskEvent;
  isSaving: boolean;
  onPick: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: `stack-row-${event.task_id}`,
      data: { taskId: event.task_id, fromStack: true },
    });

  // We deliberately do NOT close the dropdown on drag start. Closing the
  // popover unmounts this row mid-drag → dnd-kit loses its draggable
  // reference → the drop event never fires. Keeping the popover open while
  // the row's CSS transform translates it gives the user a clean drag
  // gesture; the popover is closed by handleDragEnd in the parent after
  // the move completes (or by click-outside / ESC).

  const priorityClass =
    PRIORITY_BADGE_CLASSES[event.priority] ?? PRIORITY_BADGE_CLASSES.none;

  return (
    <button
      ref={setNodeRef}
      type="button"
      onClick={(e) => {
        // dnd-kit fires click only when no drag occurred (sensor distance
        // gate). We still guard here for safety against pointer-up races.
        if (isDragging) {
          e.preventDefault();
          return;
        }
        onPick();
      }}
      style={{
        transform: CSS.Translate.toString(transform),
      }}
      {...listeners}
      {...attributes}
      className={cn(
        "group/row w-full flex items-center gap-2 rounded px-2 py-2 text-left transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:bg-primary/5 cursor-grab",
        isDragging && "opacity-50 shadow-lg z-50 cursor-grabbing",
        isSaving && "opacity-60",
      )}
      title={`${event.title} — kéo để chuyển sang giờ khác`}
    >
      <span
        className="material-symbols-outlined text-[16px] text-primary shrink-0"
        style={{ fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 18" }}
        aria-hidden="true"
      >
        task_alt
      </span>
      <div className="flex-1 min-w-0 flex flex-col gap-0.5">
        <span className="text-xs font-medium text-foreground truncate">
          {event.title}
        </span>
        <span className="text-[10px] text-muted-foreground tabular-nums">
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
    </button>
  );
}

/**
 * Habit row inside a TaskStackCard dropdown. Click-only — habits run on a
 * recurring template (`preferred_time` + `active_days`) so dragging a single
 * occurrence to a new slot is meaningless. Click forwards to the host page's
 * `onHabitClick`, which opens the calendar's habit-status popover.
 *
 * Visual mirrors HabitEventCard's tone-colored dashed border so users can
 * tell at a glance "this row is a habit, not a task".
 */
function StackRowHabit({
  event,
  isSaving,
  onPick,
}: {
  event: CalendarHabitEvent;
  isSaving?: boolean;
  onPick: () => void;
}) {
  const tone = stateTones(event.state);
  // Same per-occurrence id rule as HabitEventCard. The stack dropdown only
  // shows ONE habit row per (habit, day), so collisions across days don't
  // happen here, but keying by occurrenceDate keeps handleDragEnd uniform
  // across both drag sources.
  const occurrenceDate = (() => {
    const d = parseIsoLocal(event.start);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  })();
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: `stack-row-habit-${event.habit_id}-${occurrenceDate}`,
      data: {
        habitId: event.habit_id,
        occurrenceDate,
        // `fromHabitStack` differentiates from `fromStack` (task rows) — the
        // calendar's handleDragEnd routes the two to different endpoints.
        fromHabitStack: true,
      },
    });
  // Urgent habits that ended up inside a stack are deliberately overlapping
  // a task — backend chose NOT to shift them because the user marked them
  // critical. Surface that with a red warning chip so the user can decide
  // whether to reschedule the task or dismiss the habit for the day.
  const isUrgentConflict = event.priority === "urgent";
  return (
    <button
      ref={setNodeRef}
      type="button"
      onClick={(e) => {
        if (isDragging) {
          e.preventDefault();
          return;
        }
        onPick();
      }}
      style={{
        transform: CSS.Translate.toString(transform),
      }}
      {...listeners}
      {...attributes}
      className={cn(
        "group/row w-full flex items-center gap-2 rounded px-2 py-2 text-left transition-colors hover:bg-secondary/40 focus-visible:outline-none focus-visible:bg-secondary/40 cursor-grab",
        isDragging && "opacity-50 shadow-lg z-50 cursor-grabbing",
        isSaving && !isDragging && "opacity-60",
      )}
      title={
        isDragging
          ? "Đang kéo thói quen..."
          : isUrgentConflict
            ? `${event.title} — thói quen khẩn cấp đang trùng giờ công việc; kéo để đổi giờ`
            : `${event.title} — kéo để đổi giờ thói quen`
      }
    >
      <span
        className={cn(
          "inline-flex h-6 w-6 items-center justify-center rounded-md border border-dashed shrink-0",
          tone.surface,
          tone.border,
        )}
        aria-hidden="true"
      >
        <span
          className={cn("material-symbols-outlined text-[14px]", tone.icon)}
          style={{ fontVariationSettings: "'FILL' 0, 'wght' 500, 'GRAD' 0, 'opsz' 18" }}
        >
          {tone.iconName}
        </span>
      </span>
      <div className="flex-1 min-w-0 flex flex-col gap-0.5">
        <span className={cn("text-xs font-medium truncate flex items-center gap-1", tone.title)}>
          {isUrgentConflict && (
            <span
              className="material-symbols-outlined text-[14px] text-red-600 shrink-0"
              style={{ fontVariationSettings: "'FILL' 1, 'wght' 600, 'GRAD' 0, 'opsz' 18" }}
              aria-label="Thói quen khẩn cấp trùng giờ"
              title="Thói quen khẩn cấp đang trùng giờ công việc"
            >
              warning
            </span>
          )}
          <span className="truncate">{event.title}</span>
        </span>
        <span className={cn("text-[10px] tabular-nums truncate", tone.subdued)}>
          {formatTimeRange(event.start, event.end)}
          {event.shift_reason ? ` · ${event.shift_reason}` : ""}
        </span>
      </div>
      <span
        className={cn(
          "text-[10px] shrink-0 px-1.5 py-0.5 rounded font-medium",
          isUrgentConflict
            ? "bg-red-50 text-red-700 border border-red-200"
            : "text-muted-foreground/70",
        )}
      >
        {isUrgentConflict ? "Khẩn cấp" : "Thói quen"}
      </span>
    </button>
  );
}

function HabitEventCard({
  event,
  topPx,
  heightPx,
  isActive,
  isSaving,
  onClick,
  popoverContent,
}: {
  event: CalendarHabitEvent;
  topPx: number;
  heightPx: number;
  isActive: boolean;
  isSaving?: boolean;
  onClick: () => void;
  popoverContent?: React.ReactNode;
}) {
  const stateTone = stateTones(event.state);
  // Per-occurrence draggable id. Using just `habit-${habit_id}` would make
  // dnd-kit treat all 7 weekday cards of the same habit as ONE draggable —
  // dragging Wednesday would visually drag every weekday and the drop handler
  // would fall back to the first match (Monday). The occurrenceDate suffix
  // gives each card its own identity AND lets handleDragEnd read the date
  // straight from active.data without scanning the events list.
  const occurrenceDate = (() => {
    const d = parseIsoLocal(event.start);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  })();
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: `habit-${event.habit_id}-${occurrenceDate}`,
      data: {
        habitId: event.habit_id,
        occurrenceDate,
        originalTopPx: topPx,
      },
    });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "absolute left-1 right-1 z-10",
        isDragging && "z-30",
      )}
      style={{
        top: topPx,
        height: heightPx,
        transform: CSS.Translate.toString(transform),
      }}
    >
      <button
        type="button"
        onClick={(e) => {
          if (isDragging) {
            e.preventDefault();
            return;
          }
          onClick();
        }}
        {...listeners}
        {...attributes}
        className={cn(
          "group relative flex h-full w-full flex-col justify-center gap-1 overflow-hidden rounded-md border-2 border-dashed text-left px-2 py-1.5 transition-all cursor-grab",
          stateTone.surface,
          stateTone.border,
          "hover:shadow-sm",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
          isActive && "ring-2 ring-primary/60",
          isDragging && "opacity-50 shadow-lg cursor-grabbing",
          isSaving && !isDragging && "opacity-60",
        )}
        title={
          isDragging
            ? "Đang kéo..."
            : `${event.title} — kéo để đổi giờ thói quen`
        }
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
