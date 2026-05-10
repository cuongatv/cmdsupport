"use client";

import type { TaskDashboard, TaskPriority } from "@/lib/task-types";
import { formatTaskDate } from "@/lib/task-types";
import { translateStateName } from "@/lib/task-i18n";
import { EmptyState } from "@/components/shared/empty-state";

const STATE_GROUP_LABELS: Record<string, string> = {
  backlog: "Tồn đọng",
  todo: "Chưa bắt đầu",
  in_progress: "Đang thực hiện",
  in_review: "Đang xem xét",
  done: "Hoàn thành",
  cancelled: "Đã huỷ",
};

const STATE_GROUP_TONE: Record<string, string> = {
  backlog: "bg-muted text-muted-foreground",
  todo: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-200",
  in_progress:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200",
  in_review:
    "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-200",
  done: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200",
  cancelled:
    "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200",
};

const PRIORITY_LABELS: Record<TaskPriority, string> = {
  none: "Không có",
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  urgent: "Khẩn cấp",
};

const PRIORITY_TONE: Record<TaskPriority, string> = {
  none: "bg-muted text-muted-foreground",
  low: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-200",
  medium:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200",
  high: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-200",
  urgent: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200",
};

type TaskDashboardProps = {
  dashboard: TaskDashboard;
};

export function TaskDashboardWidgets({ dashboard }: TaskDashboardProps) {
  const { by_state, by_assignee, overdue_count, due_this_week, total_tasks } =
    dashboard;

  if (total_tasks === 0) {
    return (
      <div
        className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara"
        data-testid="task-dashboard-empty"
      >
        <EmptyState
          icon="checklist"
          title="Chưa có công việc nào"
          description="Tạo công việc đầu tiên để xem các chỉ số dự án ở đây."
        />
      </div>
    );
  }

  // Bar widths are scaled to the largest count in each list to keep the
  // smallest non-zero buckets visually meaningful. Falls back to 1 when the
  // list is empty so we never divide by zero.
  const maxStateCount = by_state.reduce(
    (acc, s) => Math.max(acc, s.count),
    0
  );
  const stateDenominator = maxStateCount > 0 ? maxStateCount : 1;
  const maxAssigneeCount = by_assignee.reduce(
    (acc, a) => Math.max(acc, a.count),
    0
  );
  const assigneeDenominator = maxAssigneeCount > 0 ? maxAssigneeCount : 1;
  const dueCount = due_this_week.length;

  return (
    <div className="flex flex-col gap-5" data-testid="task-dashboard">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div
          className="rounded-xl border border-border bg-card p-5 shadow-sahara"
          data-testid="task-dashboard-total"
        >
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <span className="material-symbols-outlined text-base">
              checklist
            </span>
            Tổng cộng
          </div>
          <div className="mt-2 text-4xl font-semibold tabular-nums text-foreground">
            {total_tasks}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            công việc trong dự án
          </p>
        </div>

        <div
          className={`rounded-xl border p-5 shadow-sahara ${
            overdue_count > 0
              ? "border-destructive/40 bg-destructive/5"
              : "border-border bg-card"
          }`}
          data-testid="task-dashboard-overdue"
        >
          <div
            className={`flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider ${
              overdue_count > 0 ? "text-destructive" : "text-muted-foreground"
            }`}
          >
            <span className="material-symbols-outlined text-base">warning</span>
            Quá hạn
          </div>
          <div
            className={`mt-2 text-4xl font-semibold tabular-nums ${
              overdue_count > 0 ? "text-destructive" : "text-foreground"
            }`}
          >
            {overdue_count}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            công việc đã quá hạn cần xử lý ngay
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section
          className="rounded-xl border border-border bg-card shadow-sahara"
          data-testid="task-dashboard-by-state"
        >
          <header className="border-b border-border px-5 py-3">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <span className="material-symbols-outlined text-base text-muted-foreground">
                view_column
              </span>
              Theo trạng thái
            </h3>
          </header>
          <div className="flex flex-col gap-3 p-5">
            {by_state.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Chưa có trạng thái nào.
              </p>
            ) : (
              by_state.map((item) => {
                const widthPct = Math.round(
                  (item.count / stateDenominator) * 100
                );
                const groupLabel =
                  STATE_GROUP_LABELS[item.group] ?? item.group;
                const groupTone =
                  STATE_GROUP_TONE[item.group] ?? STATE_GROUP_TONE.backlog;
                const stateLabel = translateStateName(item.state_name);
                return (
                  <div
                    key={item.state_id}
                    className="flex flex-col gap-1.5"
                    data-testid={`task-dashboard-state-${item.state_id}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <span
                          className="truncate text-sm font-medium text-foreground"
                          title={stateLabel}
                        >
                          {stateLabel}
                        </span>
                        <span
                          className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${groupTone}`}
                        >
                          {groupLabel}
                        </span>
                      </div>
                      <span className="shrink-0 text-sm font-semibold tabular-nums text-foreground">
                        {item.count}
                      </span>
                    </div>
                    <div
                      className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                      role="progressbar"
                      aria-label={`${stateLabel}: ${item.count} công việc`}
                      aria-valuenow={item.count}
                      aria-valuemin={0}
                      aria-valuemax={total_tasks}
                    >
                      <div
                        className="h-full rounded-full bg-primary/70 transition-all"
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>

        <section
          className="rounded-xl border border-border bg-card shadow-sahara"
          data-testid="task-dashboard-by-assignee"
        >
          <header className="border-b border-border px-5 py-3">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <span className="material-symbols-outlined text-base text-muted-foreground">
                group
              </span>
              Theo người thực hiện
            </h3>
          </header>
          <div className="flex flex-col gap-3 p-5">
            {by_assignee.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Chưa có người được giao công việc nào.
              </p>
            ) : (
              by_assignee.map((item) => {
                const widthPct = Math.round(
                  (item.count / assigneeDenominator) * 100
                );
                return (
                  <div
                    key={item.employee_id}
                    className="flex flex-col gap-1.5"
                    data-testid={`task-dashboard-assignee-${item.employee_id}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="truncate text-sm font-medium text-foreground">
                        {item.employee_name}
                      </span>
                      <span className="shrink-0 text-sm font-semibold tabular-nums text-foreground">
                        {item.count}
                      </span>
                    </div>
                    <div
                      className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                      role="progressbar"
                      aria-label={`${item.employee_name}: ${item.count} công việc`}
                      aria-valuenow={item.count}
                      aria-valuemin={0}
                      aria-valuemax={total_tasks}
                    >
                      <div
                        className="h-full rounded-full bg-primary/60 transition-all"
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>
      </div>

      <section
        className="rounded-xl border border-border bg-card shadow-sahara"
        data-testid="task-dashboard-due-this-week"
      >
        <header className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <span className="material-symbols-outlined text-base text-muted-foreground">
              event
            </span>
            Trong tuần này
          </h3>
          <span className="tabular-nums text-xs text-muted-foreground">
            {dueCount} công việc
          </span>
        </header>
        <div className="flex flex-col">
          {dueCount === 0 ? (
            <p className="px-5 py-8 text-center text-xs text-muted-foreground">
              Không có công việc nào đến hạn trong tuần này.
            </p>
          ) : (
            due_this_week.map((item) => {
              const priorityLabel =
                PRIORITY_LABELS[item.priority] ?? item.priority;
              const priorityTone =
                PRIORITY_TONE[item.priority] ?? PRIORITY_TONE.none;
              return (
                <div
                  key={item.id}
                  className="flex items-center justify-between gap-3 border-b border-border px-5 py-3 last:border-b-0"
                  data-testid={`task-dashboard-due-${item.id}`}
                >
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="truncate text-sm font-medium text-foreground">
                      {item.title}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {translateStateName(item.state_name)}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span
                      className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${priorityTone}`}
                    >
                      {priorityLabel}
                    </span>
                    <span className="tabular-nums text-xs text-muted-foreground">
                      {formatTaskDate(item.due_date)}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>
    </div>
  );
}
