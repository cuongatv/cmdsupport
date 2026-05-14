/**
 * Personal habits, calendar, and dashboard API types.
 *
 * Mirrors `app/schemas/habits.py` exactly. Whenever the Pydantic models
 * change, update this file in lockstep — there is no runtime validation on
 * the frontend, so drift surfaces as a runtime "undefined" only.
 */

export type TaskPriority = "none" | "low" | "medium" | "high" | "urgent";

export type HabitOccurrenceStatus = "completed" | "skipped" | "shifted";

export type CalendarEventType = "task" | "habit";

export type HabitCreate = {
  title: string;
  priority: TaskPriority;
  preferred_time: string; // "HH:MM:SS"
  duration_minutes: number;
  active_days: number[]; // 0..6 (Mon..Sun, matches date.weekday())
  is_active: boolean;
};

export type HabitRead = HabitCreate & {
  id: string;
  owner_employee_id: string;
  created_at: string;
  updated_at: string;
};

export type HabitUpdate = {
  title?: string;
  priority?: TaskPriority;
  preferred_time?: string;
  duration_minutes?: number;
  active_days?: number[];
  is_active?: boolean;
};

export type HabitOccurrenceStateRead = {
  id: string;
  habit_id: string;
  occurrence_date: string; // "YYYY-MM-DD"
  state: HabitOccurrenceStatus;
  actual_start: string | null; // "HH:MM:SS"
  shift_reason: string | null;
  created_at: string;
};

export type OccurrenceUpsertBody = {
  state: HabitOccurrenceStatus;
  actual_start?: string | null;
  shift_reason?: string | null;
};

export type CalendarTaskEvent = {
  event_type: "task";
  task_id: string;
  title: string;
  priority: TaskPriority;
  scheduled_start_at: string;
  scheduled_end_at: string;
  schedule_locked: boolean;
};

export type CalendarHabitEvent = {
  event_type: "habit";
  habit_id: string;
  title: string;
  priority: TaskPriority;
  start: string;
  end: string;
  original_start: string | null;
  shift_reason: string | null;
  state: HabitOccurrenceStatus | null;
};

export type CalendarEvent = CalendarTaskEvent | CalendarHabitEvent;

export type CalendarWeekResponse = {
  scope: "personal" | "department";
  week_start: string; // "YYYY-MM-DD"
  week_end: string; // "YYYY-MM-DD"
  events: CalendarEvent[];
};

export type DashboardBuckets = {
  total: number;
  not_due_yet: number;
  due_soon: number;
  overdue: number;
};

export type UnitDashboardAggregate = {
  unit_id: string;
  unit_name: string;
  unit_type: string;
  buckets: DashboardBuckets;
};

export type DashboardOverviewResponse = {
  personal: DashboardBuckets;
  units: UnitDashboardAggregate[];
  due_soon_days: number;
};
