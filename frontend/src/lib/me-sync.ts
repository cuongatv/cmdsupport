"use client";

/**
 * Cross-surface synchronization for the /me workspace.
 *
 * In-module version counters per surface. Mutation sites call `bump*`
 * after a successful write; pages subscribe via `use*Version()` hooks
 * and put the returned number in their data-loading effect's dep list,
 * so a bump triggers a re-fetch. `useFocusBump()` bumps every surface
 * when the tab regains focus — a cheap stale-check substitute for
 * polling.
 *
 * No state-management library — this is plain module-scoped state
 * behind React 19's built-in `useSyncExternalStore`.
 */

import { useEffect, useSyncExternalStore } from "react";

type Surface = "habits" | "calendar" | "dashboard" | "units";

const versions: Record<Surface, number> = {
  habits: 0,
  calendar: 0,
  dashboard: 0,
  units: 0,
};

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(): void {
  for (const listener of listeners) listener();
}

// ---------------------------------------------------------------------------
// Bump helpers — call after a successful mutation.
// ---------------------------------------------------------------------------

export function bumpHabitsVersion(): void {
  versions.habits += 1;
  notify();
}

export function bumpCalendarVersion(): void {
  versions.calendar += 1;
  notify();
}

export function bumpDashboardVersion(): void {
  versions.dashboard += 1;
  notify();
}

export function bumpUnitsVersion(): void {
  versions.units += 1;
  notify();
}

/**
 * Bump habits + calendar + dashboard in a single notify(). Use after any
 * habit C/U/D and after the calendar habit-popover occurrence upsert.
 */
export function bumpAfterHabitMutation(): void {
  versions.habits += 1;
  versions.calendar += 1;
  versions.dashboard += 1;
  notify();
}

/**
 * Bump calendar + dashboard only. Use after the habits-page today-toggle
 * so that the habits page itself does NOT refetch and clobber its
 * optimistic local toggle state.
 */
export function bumpAfterOccurrenceToggle(): void {
  versions.calendar += 1;
  versions.dashboard += 1;
  notify();
}

// ---------------------------------------------------------------------------
// Snapshot getters — module-scoped + stable so useSyncExternalStore doesn't
// resubscribe on every render.
// ---------------------------------------------------------------------------

const getHabits = (): number => versions.habits;
const getCalendar = (): number => versions.calendar;
const getDashboard = (): number => versions.dashboard;
const getUnits = (): number => versions.units;

// ---------------------------------------------------------------------------
// React hooks — return the current version and re-render on bumps.
// ---------------------------------------------------------------------------

export function useHabitsVersion(): number {
  return useSyncExternalStore(subscribe, getHabits, getHabits);
}

export function useCalendarVersion(): number {
  return useSyncExternalStore(subscribe, getCalendar, getCalendar);
}

export function useDashboardVersion(): number {
  return useSyncExternalStore(subscribe, getDashboard, getDashboard);
}

export function useUnitsVersion(): number {
  return useSyncExternalStore(subscribe, getUnits, getUnits);
}

/**
 * Attach a window `focus` listener that bumps every surface version when
 * the tab regains focus. Call once per /me page; listener is cheap and
 * the cleanup detaches it on unmount.
 */
export function useFocusBump(): void {
  useEffect(() => {
    function onFocus(): void {
      versions.habits += 1;
      versions.calendar += 1;
      versions.dashboard += 1;
      versions.units += 1;
      notify();
    }
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);
}
