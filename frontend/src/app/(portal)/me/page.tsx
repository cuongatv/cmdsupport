"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getDashboard } from "@/lib/habit-api";
import type {
  DashboardBuckets,
  DashboardOverviewResponse,
  UnitDashboardAggregate,
} from "@/lib/habit-types";
import type { PaginatedResponse, Task } from "@/lib/task-types";
import { formatTaskDate } from "@/lib/task-types";
import { PageHeader } from "@/components/shared/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { TASK_PRIORITY_LABELS } from "@/components/tasks/task-list-filters";
import { useDashboardVersion, useFocusBump } from "@/lib/me-sync";
import { cn } from "@/lib/utils";

const TODAY_FORMATTER = new Intl.DateTimeFormat("vi-VN", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

const PRIORITY_CLASSES: Record<string, string> = {
  none: "border-border text-muted-foreground bg-background",
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  high: "bg-orange-50 text-orange-700 border-orange-200",
  urgent: "bg-red-50 text-red-700 border-red-200",
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export default function MeDashboardPage() {
  const { user } = useAuth();
  const [overview, setOverview] = useState<DashboardOverviewResponse | null>(
    null,
  );
  const [upcoming, setUpcoming] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Subscribe to dashboard-surface invalidations + tab-focus stale checks.
  // Putting `dashboardVersion` in the effect dep list below means any bump
  // (habit C/U/D, occurrence upsert, focus regain) triggers a re-fetch.
  const dashboardVersion = useDashboardVersion();
  useFocusBump();

  // Local retry counter — the "Thử lại" button bumps this, which is part of
  // the data effect's dep list, so the user can re-attempt a failed load
  // without leaving the page.
  const [reloadTick, setReloadTick] = useState(0);
  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  useEffect(() => {
    // setTimeout(0) defers the setLoading/setOverview calls out of the
    // effect tick — matches the admin pages and silences the React 19
    // `react-hooks/set-state-in-effect` lint. The `cancelled` flag prevents
    // stale state writes if the effect re-runs (or the component unmounts)
    // before the in-flight Promise.all settles — important under React 19's
    // double-invoke strict mode and during route transitions.
    let cancelled = false;
    const timerId = window.setTimeout(() => {
      setLoading(true);
      setError("");
      void (async () => {
        try {
          // The dashboard relies on two endpoints: /api/me/dashboard for the
          // buckets and /api/me/tasks (sorted by due_date asc, page_size=5)
          // for the "Sắp tới" list. Fetched in parallel so the first paint
          // isn't serialized.
          const [dashboardData, upcomingData] = await Promise.all([
            getDashboard(),
            api<PaginatedResponse<Task>>(
              "/api/me/tasks?sort_by=due_date&sort_dir=asc&page=1&page_size=5",
            ),
          ]);
          if (cancelled) return;
          setOverview(dashboardData);
          setUpcoming(upcomingData.items);
        } catch (err) {
          if (cancelled) return;
          setOverview(null);
          setUpcoming([]);
          setError(getErrorMessage(err, "Không tải được tổng quan công việc"));
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [dashboardVersion, reloadTick]);

  const today = TODAY_FORMATTER.format(new Date());
  const personal = overview?.personal ?? null;
  const units = overview?.units ?? [];

  return (
    <>
      <PageHeader
        title={user ? `Xin chào, ${user.name}` : "Không gian làm việc cá nhân"}
        description={today.charAt(0).toUpperCase() + today.slice(1)}
        action={
          <Link
            href="/me/tasks"
            className={cn(
              buttonVariants({ variant: "default" }),
              "min-h-[40px] px-3 sm:min-h-8 sm:px-2.5 bg-primary text-primary-foreground hover:bg-primary/90",
            )}
          >
            <span className="material-symbols-outlined text-sm">checklist</span>
            Công việc của tôi
          </Link>
        }
      />

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
            className="min-h-[40px] sm:min-h-7 self-start sm:self-auto border-destructive/30 text-destructive hover:bg-destructive/10"
          >
            <span className="material-symbols-outlined text-sm">refresh</span>
            Thử lại
          </Button>
        </div>
      )}

      {/* Personal stat cards */}
      <section aria-labelledby="me-personal-buckets" className="flex flex-col gap-3">
        <h3
          id="me-personal-buckets"
          className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
        >
          Công việc cá nhân
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon="assignment"
            label="Tổng số"
            value={personal?.total ?? 0}
            loading={loading}
            accent="primary"
          />
          <StatCard
            icon="warning"
            label="Quá hạn"
            value={personal?.overdue ?? 0}
            loading={loading}
            accent="red"
          />
          <StatCard
            icon="schedule"
            label="Sắp đến hạn"
            value={personal?.due_soon ?? 0}
            loading={loading}
            accent="amber"
            hint={
              overview ? `Trong ${overview.due_soon_days} ngày tới` : undefined
            }
          />
          <StatCard
            icon="event_available"
            label="Chưa tới hạn"
            value={personal?.not_due_yet ?? 0}
            loading={loading}
            accent="green"
          />
        </div>
      </section>

      {/* Units summary + upcoming side by side on desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Units */}
        <section
          aria-labelledby="me-units-summary"
          className="lg:col-span-3 flex flex-col gap-3"
        >
          <div className="flex items-end justify-between">
            <h3
              id="me-units-summary"
              className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
            >
              Đơn vị của tôi
            </h3>
            <Link
              href="/me/units"
              className="text-xs font-medium text-primary hover:underline"
            >
              Xem tất cả
            </Link>
          </div>
          <UnitsSummary loading={loading} units={units} />
        </section>

        {/* Upcoming */}
        <section
          aria-labelledby="me-upcoming"
          className="lg:col-span-2 flex flex-col gap-3"
        >
          <div className="flex items-end justify-between">
            <h3
              id="me-upcoming"
              className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
            >
              Sắp tới
            </h3>
            <Link
              href="/me/tasks?sort_by=due_date&sort_dir=asc"
              className="text-xs font-medium text-primary hover:underline"
            >
              Tất cả
            </Link>
          </div>
          <UpcomingTasks loading={loading} tasks={upcoming} />
        </section>
      </div>
    </>
  );
}

type StatCardProps = {
  icon: string;
  label: string;
  value: number;
  loading: boolean;
  accent: "primary" | "red" | "amber" | "green";
  hint?: string;
};

function StatCard({ icon, label, value, loading, accent, hint }: StatCardProps) {
  // BIDV teal is the brand primary; the other three buckets borrow semantic
  // colors but stay tonal (no neon backgrounds) to match the rest of the
  // portal's calm density.
  const ACCENT: Record<StatCardProps["accent"], { wrap: string; icon: string; value: string }> = {
    primary: {
      wrap: "bg-primary/10 border-primary/20",
      icon: "text-primary",
      value: "text-primary",
    },
    red: {
      wrap: "bg-red-50 border-red-200",
      icon: "text-red-600",
      value: "text-red-700",
    },
    amber: {
      wrap: "bg-amber-50 border-amber-200",
      icon: "text-amber-600",
      value: "text-amber-700",
    },
    green: {
      wrap: "bg-emerald-50 border-emerald-200",
      icon: "text-emerald-600",
      value: "text-emerald-700",
    },
  };
  const tone = ACCENT[accent];

  return (
    <div className="bg-card rounded-xl border border-border shadow-sahara p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <span
          className={`flex h-9 w-9 items-center justify-center rounded-lg border ${tone.wrap}`}
        >
          <span
            className={`material-symbols-outlined text-base ${tone.icon}`}
            style={{
              fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
            }}
          >
            {icon}
          </span>
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        {loading ? (
          // Skeleton block sized to the eventual 3xl-bold numeral so the
          // layout doesn't reflow once data lands.
          <div className="h-8 w-12 rounded-md bg-muted animate-pulse" />
        ) : (
          <span
            className={`text-3xl font-bold tabular-nums tracking-tight ${tone.value}`}
          >
            {value}
          </span>
        )}
      </div>
      {hint && (
        <span className="text-xs text-muted-foreground">{hint}</span>
      )}
    </div>
  );
}

function UnitsSummary({
  loading,
  units,
}: {
  loading: boolean;
  units: UnitDashboardAggregate[];
}) {
  if (loading) {
    // Skeleton rows mirror the real UnitRow shape (icon + 2-line text +
    // optional bucket tags) so the layout doesn't jump when data arrives.
    return (
      <div
        className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara divide-y divide-border"
        aria-busy="true"
        aria-label="Đang tải đơn vị"
      >
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="flex items-center gap-4 px-5 py-4 animate-pulse"
          >
            <div className="h-10 w-10 rounded-lg bg-muted shrink-0" />
            <div className="flex-1 min-w-0 flex flex-col gap-1.5">
              <div className="h-4 w-40 max-w-full rounded bg-muted" />
              <div className="h-3 w-24 max-w-full rounded bg-muted" />
            </div>
            <div className="hidden sm:flex items-center gap-3">
              <div className="h-6 w-12 rounded-md bg-muted" />
              <div className="h-6 w-14 rounded-md bg-muted" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (units.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-card/50 py-10 px-4 flex flex-col items-center text-center gap-2">
        <span
          className="material-symbols-outlined text-3xl text-muted-foreground/50"
          style={{ fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 24" }}
        >
          domain
        </span>
        <p className="text-sm font-medium text-foreground">
          Bạn chưa thuộc đơn vị nào
        </p>
        <p className="text-xs text-muted-foreground max-w-sm">
          Khi quản trị viên thêm bạn vào một đơn vị, các thống kê công việc của
          đơn vị sẽ hiển thị tại đây.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara divide-y divide-border">
      {units.map((unit) => (
        <UnitRow key={unit.unit_id} unit={unit} />
      ))}
    </div>
  );
}

function UnitRow({ unit }: { unit: UnitDashboardAggregate }) {
  const buckets: DashboardBuckets = unit.buckets;
  return (
    <Link
      href={`/me/units/${unit.unit_id}`}
      className="group flex items-center gap-4 px-5 py-4 hover:bg-secondary/30 transition-colors"
    >
      <span
        className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0"
        aria-hidden="true"
      >
        <span
          className="material-symbols-outlined text-lg"
          style={{ fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
        >
          domain
        </span>
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-foreground truncate">
          {unit.unit_name}
        </p>
        <p className="text-xs text-muted-foreground capitalize truncate">
          {unit.unit_type}
        </p>
      </div>
      <div className="hidden sm:flex items-center gap-3 text-xs">
        <BucketTag value={buckets.total} label="Tổng" />
        <BucketTag value={buckets.overdue} label="Quá hạn" tone="red" />
        <BucketTag value={buckets.due_soon} label="Sắp tới" tone="amber" />
      </div>
      <div className="sm:hidden flex flex-col items-end gap-1 text-xs">
        <span className="font-semibold text-foreground tabular-nums">
          {buckets.total}
        </span>
        {buckets.overdue > 0 && (
          <span className="text-red-700 tabular-nums">
            {buckets.overdue} quá hạn
          </span>
        )}
      </div>
      <span className="material-symbols-outlined text-sm text-muted-foreground/40 group-hover:text-muted-foreground transition-colors">
        chevron_right
      </span>
    </Link>
  );
}

function BucketTag({
  value,
  label,
  tone = "neutral",
}: {
  value: number;
  label: string;
  tone?: "neutral" | "red" | "amber";
}) {
  const styles: Record<string, string> = {
    neutral: "bg-secondary text-secondary-foreground",
    red: value > 0 ? "bg-red-50 text-red-700" : "bg-secondary text-muted-foreground",
    amber: value > 0 ? "bg-amber-50 text-amber-700" : "bg-secondary text-muted-foreground",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-1 ${styles[tone]}`}
    >
      <span className="font-semibold tabular-nums">{value}</span>
      <span className="text-[11px] opacity-80">{label}</span>
    </span>
  );
}

function UpcomingTasks({
  loading,
  tasks,
}: {
  loading: boolean;
  tasks: Task[];
}) {
  if (loading) {
    // Skeleton list with three rows that match the real task-row shape
    // (priority pill on the left + title block + chevron). Reserves
    // vertical space without using a centered spinner.
    return (
      <ol
        className="flex flex-col gap-2"
        aria-busy="true"
        aria-label="Đang tải công việc sắp tới"
      >
        {[0, 1, 2].map((i) => (
          <li
            key={i}
            className="flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sahara animate-pulse"
          >
            <div className="h-5 w-16 rounded-md bg-muted shrink-0" />
            <div className="flex-1 flex flex-col gap-1.5 min-w-0">
              <div className="h-4 w-3/4 rounded bg-muted" />
              <div className="h-3 w-1/3 rounded bg-muted" />
            </div>
          </li>
        ))}
      </ol>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-card/50 py-10 px-4 flex flex-col items-center text-center gap-2">
        <span
          className="material-symbols-outlined text-3xl text-muted-foreground/50"
          style={{ fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 24" }}
        >
          check_circle
        </span>
        <p className="text-sm font-medium text-foreground">
          Không có công việc sắp tới
        </p>
        <p className="text-xs text-muted-foreground max-w-xs">
          Bạn đã hoàn thành mọi việc trong tầm nhìn gần.
        </p>
      </div>
    );
  }

  return (
    <ol className="flex flex-col gap-2">
      {tasks.map((task) => (
        <li key={task.id}>
          <Link
            href={`/me/tasks?task=${task.id}`}
            className="group flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sahara hover:bg-secondary/30 transition-colors"
          >
            <span
              className={`mt-0.5 inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium ${
                PRIORITY_CLASSES[task.priority] ?? PRIORITY_CLASSES.none
              }`}
            >
              {TASK_PRIORITY_LABELS[task.priority] ?? task.priority}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">
                {task.title}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground tabular-nums">
                Hạn {formatTaskDate(task.due_date)}
              </p>
            </div>
            <span className="material-symbols-outlined text-sm text-muted-foreground/40 group-hover:text-muted-foreground transition-colors">
              chevron_right
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

