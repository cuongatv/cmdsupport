/**
 * Habit, calendar, and personal-dashboard API client.
 *
 * Wraps the `/api/me/*` surface exposed by `app/routers/habits.py`. Every
 * call goes through `api()` from `@/lib/api`, which handles auth, base URL,
 * timeouts, JSON serialization, and FastAPI-style error decoding.
 */
import { api } from "@/lib/api";
import type { Task, TaskPriority } from "@/lib/task-types";
import type {
  CalendarWeekResponse,
  DashboardOverviewResponse,
  HabitCreate,
  HabitOccurrenceStateRead,
  HabitRead,
  HabitUpdate,
  OccurrenceUpsertBody,
} from "./habit-types";

// ---------------------------------------------------------------------------
// Personal task creation (POST /api/me/tasks)
// ---------------------------------------------------------------------------

export type PersonalTaskCreate = {
  title: string;
  description?: string | null;
  priority?: TaskPriority;
  due_date?: string | null; // ISO 8601 with offset (server stores UTC)
};

export function createPersonalTask(body: PersonalTaskCreate): Promise<Task> {
  return api<Task>("/api/me/tasks", { method: "POST", body });
}

export type PersonalTaskUpdate = Partial<{
  title: string;
  description: string | null;
  priority: TaskPriority;
  due_date: string | null;
}>;

/**
 * Patch an owner-scoped task (`/api/me/tasks/{id}`). Used by the calendar
 * drag-drop to push a new `due_date`. Backend rejects non-owner edits with 404.
 */
export function updatePersonalTask(
  id: string,
  body: PersonalTaskUpdate,
): Promise<Task> {
  return api<Task>(`/api/me/tasks/${id}`, { method: "PATCH", body });
}

// ---------------------------------------------------------------------------
// Habit CRUD
// ---------------------------------------------------------------------------

export function listHabits(): Promise<HabitRead[]> {
  return api<HabitRead[]>("/api/me/habits");
}

export function createHabit(body: HabitCreate): Promise<HabitRead> {
  return api<HabitRead>("/api/me/habits", { method: "POST", body });
}

export function getHabit(id: string): Promise<HabitRead> {
  return api<HabitRead>(`/api/me/habits/${id}`);
}

export function updateHabit(id: string, body: HabitUpdate): Promise<HabitRead> {
  return api<HabitRead>(`/api/me/habits/${id}`, { method: "PATCH", body });
}

export function deleteHabit(id: string): Promise<void> {
  return api<void>(`/api/me/habits/${id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Habit occurrence state — per-date upsert
// ---------------------------------------------------------------------------

export function upsertOccurrence(
  habitId: string,
  date: string,
  body: OccurrenceUpsertBody,
): Promise<HabitOccurrenceStateRead> {
  return api<HabitOccurrenceStateRead>(
    `/api/me/habits/${habitId}/occurrences/${date}`,
    { method: "POST", body },
  );
}

// ---------------------------------------------------------------------------
// Calendar week view
// ---------------------------------------------------------------------------

export function getCalendarWeek(
  weekStart: string,
  scope: "personal" | "department" = "personal",
  deptId?: string,
): Promise<CalendarWeekResponse> {
  const params = new URLSearchParams({ week_start: weekStart, scope });
  if (deptId) params.set("dept_id", deptId);
  return api<CalendarWeekResponse>(`/api/me/calendar?${params.toString()}`);
}

// ---------------------------------------------------------------------------
// Personal dashboard overview
// ---------------------------------------------------------------------------

export function getDashboard(): Promise<DashboardOverviewResponse> {
  return api<DashboardOverviewResponse>("/api/me/dashboard");
}
