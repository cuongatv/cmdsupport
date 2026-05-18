"use client";

import * as React from "react";
import { ApiError } from "@/lib/api";
import { FEATURE_AGILE_PHASE_5 } from "@/lib/feature-flags";
import { getFlowMetrics, getThroughput } from "@/lib/task-api";
import type {
  FlowThroughput,
  Sprint,
  TaskFlowSnapshot,
} from "@/lib/task-types";

// Phase 5 (FEATURE_AGILE_PHASE_5) — Vietnamese flow metrics panel.
// Read-only projection of:
//   - `GET /api/task-projects/{id}/flow-metrics` (snapshot list)
//   - `GET /api/task-projects/{id}/throughput`   (completed totals)
//
// Strings are hardcoded Vietnamese per the project decision to avoid
// pulling in an i18n framework. Hidden entirely when the flag is OFF so
// legacy deployments + earlier-phase rollouts stay untouched.
//
// Deliberately renders SIMPLE metric cards / table — no burndown,
// velocity, retrospective, or forecasting charts (per the agile-upgrade
// plan). No charting library is introduced.

type FlowMetricsPanelProps = {
  projectId: string;
  // Active sprint, optional. When provided, the panel surfaces two extra
  // cards driven by throughput inside the sprint's date window:
  //   - "Cam kết Sprint" — story points across the sprint window
  //   - "Hoàn thành trong Sprint" — tasks closed inside the window
  // When `null` / `undefined`, the sprint section is hidden entirely.
  activeSprint?: Sprint | null;
};

// 14-day default range. The choice mirrors the snapshot retention horizon
// most agile dashboards default to and keeps the throughput count stable
// across daily refreshes.
const DEFAULT_LOOKBACK_DAYS = 14;

function isFlagOn(): boolean {
  return FEATURE_AGILE_PHASE_5;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

function toIsoDate(value: Date): string {
  // `toISOString()` would emit `YYYY-MM-DDTHH:MM:SS.sssZ`. FastAPI happily
  // parses just the date prefix; trimming keeps the URL readable.
  const yyyy = value.getFullYear();
  const mm = String(value.getMonth() + 1).padStart(2, "0");
  const dd = String(value.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function daysBetween(start: string, end: string): number {
  const startMs = new Date(`${start}T00:00:00Z`).getTime();
  const endMs = new Date(`${end}T00:00:00Z`).getTime();
  if (Number.isNaN(startMs) || Number.isNaN(endMs)) return 0;
  const diffDays = Math.round((endMs - startMs) / (1000 * 60 * 60 * 24));
  return Math.max(0, diffDays + 1);
}

// Cycle-time approximation using Little's Law: avg WIP / throughput rate.
// We compute it from the snapshot inventory (sum of task_count across the
// latest snapshot) divided by the throughput rate. When throughput is zero
// the metric is undefined — render `"—"`.
function approximateCycleDays(
  totalActiveInventory: number,
  tasksCompleted: number,
  windowDays: number,
): string {
  if (tasksCompleted <= 0 || windowDays <= 0) return "—";
  const rate = tasksCompleted / windowDays;
  if (rate <= 0) return "—";
  const cycle = totalActiveInventory / rate;
  return `${cycle.toFixed(1)} ngày`;
}

// Lead-time approximation: same Little's Law projection across the entire
// snapshot history in the window (not just the latest). This is purposely
// less optimistic than cycle time — it folds in queue depth across the
// observation window so the number nudges teams toward shorter queues.
function approximateLeadDays(
  snapshots: TaskFlowSnapshot[],
  tasksCompleted: number,
  windowDays: number,
): string {
  if (tasksCompleted <= 0 || windowDays <= 0 || snapshots.length === 0) {
    return "—";
  }
  // Group by snapshot_date so we can average inventory size per day,
  // ignoring per-state breakdown.
  const byDate: Record<string, number> = {};
  for (const row of snapshots) {
    byDate[row.snapshot_date] = (byDate[row.snapshot_date] ?? 0) + row.task_count;
  }
  const totals = Object.values(byDate);
  if (totals.length === 0) return "—";
  const avgInventory = totals.reduce((a, b) => a + b, 0) / totals.length;
  const rate = tasksCompleted / windowDays;
  if (rate <= 0) return "—";
  const lead = avgInventory / rate;
  return `${lead.toFixed(1)} ngày`;
}

function sumLatestSnapshot(
  snapshots: TaskFlowSnapshot[],
  field: "task_count" | "blocked_count",
): number {
  if (snapshots.length === 0) return 0;
  // Snapshots are ordered oldest-first by the backend; find the latest
  // snapshot_date and sum across its rows (one per state).
  const sorted = [...snapshots].sort((a, b) =>
    a.snapshot_date < b.snapshot_date ? 1 : -1,
  );
  const latestDate = sorted[0].snapshot_date;
  let total = 0;
  for (const row of sorted) {
    if (row.snapshot_date !== latestDate) break;
    total += row[field];
  }
  return total;
}

type MetricCardProps = {
  label: string;
  value: string;
  hint?: string;
  testId: string;
};

function MetricCard({ label, value, hint, testId }: MetricCardProps) {
  return (
    <div
      className="flex flex-col gap-1 rounded-xl border border-border bg-background px-4 py-3"
      data-testid={testId}
    >
      <span className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="text-2xl font-semibold tracking-tight text-foreground">
        {value}
      </span>
      {hint && (
        <span className="text-[11px] text-muted-foreground">{hint}</span>
      )}
    </div>
  );
}

export function FlowMetricsPanel({
  projectId,
  activeSprint,
}: FlowMetricsPanelProps) {
  const [snapshots, setSnapshots] = React.useState<TaskFlowSnapshot[]>([]);
  const [throughput, setThroughput] = React.useState<FlowThroughput | null>(
    null,
  );
  const [sprintThroughput, setSprintThroughput] =
    React.useState<FlowThroughput | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string>("");

  // Lock the default range to the component's mount time so daily refreshes
  // stay deterministic. Re-fetching is driven by `projectId` / `activeSprint`
  // changes only.
  const [range] = React.useState(() => {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - DEFAULT_LOOKBACK_DAYS + 1);
    return {
      startDate: toIsoDate(start),
      endDate: toIsoDate(end),
    };
  });

  const refresh = React.useCallback(async () => {
    if (!isFlagOn()) return;
    setLoading(true);
    setError("");
    try {
      const [snapshotRows, throughputData] = await Promise.all([
        getFlowMetrics(projectId, range.startDate, range.endDate),
        getThroughput(projectId, range.startDate, range.endDate),
      ]);
      setSnapshots(snapshotRows);
      setThroughput(throughputData);
      if (activeSprint && activeSprint.start_date && activeSprint.end_date) {
        // The sprint window may be wider than the default lookback. Query
        // throughput separately so the sprint card reflects the sprint's
        // own dates, not the panel default.
        const sprintStart = activeSprint.start_date.slice(0, 10);
        const sprintEnd = activeSprint.end_date.slice(0, 10);
        try {
          const sprintData = await getThroughput(
            projectId,
            sprintStart,
            sprintEnd,
          );
          setSprintThroughput(sprintData);
        } catch {
          // Sprint throughput is optional; swallow errors so the main panel
          // still renders. The "Hoàn thành trong Sprint" card falls back
          // to a `—` placeholder via the null check below.
          setSprintThroughput(null);
        }
      } else {
        setSprintThroughput(null);
      }
    } catch (err) {
      setError(getErrorMessage(err, "Không tải được dữ liệu dòng chảy"));
    } finally {
      setLoading(false);
    }
  }, [projectId, range, activeSprint]);

  React.useEffect(() => {
    // Defer to a microtask to dodge `react-hooks/set-state-in-effect` per
    // the project-wide pattern (see SquadCapacityPanel).
    const timerId = window.setTimeout(() => {
      refresh();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [refresh]);

  if (!isFlagOn()) {
    // Phase 5 OFF — render nothing. Caller can mount this component
    // unconditionally; the flag check lives here so the gate is co-located
    // with the feature.
    return null;
  }

  const windowDays = daysBetween(range.startDate, range.endDate);
  const tasksCompleted = throughput?.tasks_completed ?? 0;
  const totalActiveInventory = sumLatestSnapshot(snapshots, "task_count");
  const blockedCount = sumLatestSnapshot(snapshots, "blocked_count");
  const leadValue = approximateLeadDays(
    snapshots,
    tasksCompleted,
    windowDays,
  );
  const cycleValue = approximateCycleDays(
    totalActiveInventory,
    tasksCompleted,
    windowDays,
  );

  const showSprintSection = Boolean(
    activeSprint && activeSprint.start_date && activeSprint.end_date,
  );

  return (
    <section
      className="flex flex-col gap-3 rounded-xl border border-border bg-card/40 p-4"
      data-testid="flow-metrics-panel"
    >
      <header className="flex flex-col gap-0.5">
        <h2 className="text-base font-semibold tracking-tight text-foreground">
          Chỉ số dòng chảy công việc
        </h2>
        <p className="text-xs text-muted-foreground">
          Tổng hợp {windowDays} ngày gần nhất — không có biểu đồ burndown,
          velocity hay forecasting.
        </p>
      </header>

      {error && (
        <div
          className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
          data-testid="flow-metrics-panel-error"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div
          className="text-sm text-muted-foreground"
          data-testid="flow-metrics-panel-loading"
        >
          Đang tải chỉ số dòng chảy…
        </div>
      ) : snapshots.length === 0 && tasksCompleted === 0 && !error ? (
        <div
          className="rounded-lg border border-dashed border-border bg-secondary/30 px-4 py-6 text-center text-sm text-muted-foreground"
          data-testid="flow-metrics-panel-empty"
        >
          Chưa có dữ liệu dòng chảy trong khoảng thời gian này
        </div>
      ) : (
        <div
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="flow-metrics-cards"
        >
          <MetricCard
            label="Thời gian xử lý"
            value={leadValue}
            hint="Ước lượng theo định luật Little (tồn kho trung bình / nhịp hoàn thành)."
            testId="flow-metric-lead-time"
          />
          <MetricCard
            label="Thời gian hoàn tất"
            value={cycleValue}
            hint="Ước lượng cho công việc đang mở dựa trên nhịp hoàn thành gần đây."
            testId="flow-metric-cycle-time"
          />
          <MetricCard
            label="Số việc hoàn thành"
            value={String(tasksCompleted)}
            hint={`${windowDays} ngày · ${throughput?.story_points_completed ?? 0} điểm`}
            testId="flow-metric-throughput"
          />
          <MetricCard
            label="Công việc tồn đọng lâu"
            value={String(totalActiveInventory)}
            hint="Tổng công việc đang mở từ ảnh chụp gần nhất."
            testId="flow-metric-aging"
          />
          <MetricCard
            label="Công việc đang bị chặn"
            value={String(blockedCount)}
            hint="Số công việc có lý do chặn từ ảnh chụp gần nhất."
            testId="flow-metric-blocked"
          />
        </div>
      )}

      {showSprintSection && activeSprint && (
        <div
          className="mt-2 flex flex-col gap-2 rounded-xl border border-border bg-background/60 p-3"
          data-testid="flow-metrics-sprint-section"
        >
          <h3 className="text-sm font-semibold text-foreground">
            Sprint hiện tại
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {activeSprint.name}
            </span>
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <MetricCard
              label="Cam kết Sprint"
              value={String(sprintThroughput?.story_points_completed ?? "—")}
              hint="Điểm hoàn thành tính theo khung thời gian Sprint."
              testId="flow-metric-sprint-commitment"
            />
            <MetricCard
              label="Hoàn thành trong Sprint"
              value={String(sprintThroughput?.tasks_completed ?? "—")}
              hint="Số công việc đóng trong khung thời gian Sprint."
              testId="flow-metric-sprint-completion"
            />
          </div>
        </div>
      )}

      <div
        className="mt-2 flex flex-col gap-1 rounded-xl border border-border bg-background/60 p-3"
        data-testid="flow-metrics-governance"
      >
        <h3 className="text-sm font-semibold text-foreground">
          Quy tắc điều phối
        </h3>
        <ul className="flex list-disc flex-col gap-0.5 pl-5 text-xs text-muted-foreground">
          <li>
            Vượt giới hạn việc đang làm chỉ phát cảnh báo — cần quyền
            <code className="mx-1 rounded bg-secondary px-1 font-mono text-[11px]">
              agile.wip.override
            </code>
            để bỏ qua mà không tạo dấu kiểm khuyến nghị.
          </li>
          <li>
            Đóng Sprint khi chưa hoàn tất cần quyền
            <code className="mx-1 rounded bg-secondary px-1 font-mono text-[11px]">
              agile.sprint.close
            </code>
            ; thiếu quyền sẽ ghi nhật ký cảnh báo nhưng vẫn cho đóng.
          </li>
          <li>
            Đưa công việc sang trạng thái Hoàn thành khi DoD còn dở dang cần
            quyền
            <code className="mx-1 rounded bg-secondary px-1 font-mono text-[11px]">
              agile.dod.bypass
            </code>
            ; ngược lại sẽ ghi nhật ký khuyến nghị.
          </li>
        </ul>
      </div>
    </section>
  );
}
