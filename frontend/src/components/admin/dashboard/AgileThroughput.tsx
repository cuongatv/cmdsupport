"use client";

import { useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipContentProps } from "recharts";
import type {
  AdminDashboardFlowSummaryResponse,
  ThroughputDataPoint,
} from "@/lib/task-types";

// T11 — Throughput trend chart for the Agile dashboard.
//
// Renders `chart_series.throughput_series` as a bar chart, one bar per
// completion window. Each bar is clickable and routes to
// `/admin/tasks?completed_from=...&completed_to=...` so a portal admin can
// drill into the source tasks for the window.
//
// Project terminology note: this chart shows the number of completed tasks
// per period. All Vietnamese labels use "Số việc hoàn thành"; we do not use
// the agile-estimation term for it anywhere in the UI.
//
// Data wiring lives in T14: this component is presentational and receives
// the dashboard payload via props so the shell can mount it with
// `data={null}` until the fetch is plumbed.

type AgileThroughputProps = {
  data: AdminDashboardFlowSummaryResponse | null;
  loading: boolean;
  error?: boolean;
  onRetry?: () => void;
};

type ChartRow = {
  label: string;
  period_start: string;
  period_end: string;
  tasks_completed: number;
  story_points_completed: number;
};

// BIDV teal — primary brand color from DESIGN.md / globals.css. Hard-coded
// because Recharts paints into SVG `fill` attributes that do not resolve
// `var(--token)` reliably across browsers; matches the convention used by
// AgileCfd in the sibling slot.
const BAR_COLOR = "#2D8380";

const STALE_THRESHOLD_MS = 24 * 60 * 60 * 1000;

function formatAsOf(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatChartDate(value: string): string {
  // Period boundaries arrive as `YYYY-MM-DD`. Render `DD/MM` to match the
  // CFD axis ticks; rotations stay flat across 14/30/90-day ranges.
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function formatRangeLabel(start: string, end: string): string {
  return `${formatChartDate(start)} – ${formatChartDate(end)}`;
}

function isStale(asOf: string): boolean {
  const date = new Date(asOf);
  if (Number.isNaN(date.getTime())) return false;
  return Date.now() - date.getTime() > STALE_THRESHOLD_MS;
}

function buildChartRows(series: ThroughputDataPoint[]): ChartRow[] {
  // Preserve zero-completion buckets — the chart should render an empty bar
  // for every period in the window, never collapse them to "missing".
  return series
    .slice()
    .sort((a, b) => (a.period_start < b.period_start ? -1 : 1))
    .map((point) => ({
      label: formatChartDate(point.period_start),
      period_start: point.period_start,
      period_end: point.period_end,
      tasks_completed: point.tasks_completed,
      story_points_completed: point.story_points_completed,
    }));
}

function ThroughputTooltip({
  active,
  payload,
}: TooltipContentProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }
  const raw = payload[0]?.payload as ChartRow | undefined;
  if (!raw) return null;
  return (
    <div
      className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md"
      data-testid="chart-throughput-tooltip"
    >
      <div className="font-semibold text-foreground">
        {formatRangeLabel(raw.period_start, raw.period_end)}
      </div>
      <div className="text-foreground">
        Hoàn thành: {raw.tasks_completed} việc
      </div>
      {raw.story_points_completed > 0 && (
        <div className="text-muted-foreground">
          Story points: {raw.story_points_completed}
        </div>
      )}
    </div>
  );
}

export function AgileThroughput({
  data,
  loading,
  error = false,
  onRetry,
}: AgileThroughputProps) {
  const router = useRouter();
  // Error wins over skeleton: a failed fetch should surface the retry
  // affordance, not a perpetually shimmering placeholder.
  const showError = error && data === null && !loading;

  if (showError) {
    return (
      <article
        data-testid="chart-throughput"
        className="flex flex-col gap-3 rounded-xl border border-destructive/30 bg-card p-4 sm:p-5"
      >
        <header className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Số việc hoàn thành
          </h3>
        </header>
        <div
          className="flex flex-col gap-3 rounded-lg bg-destructive/5 p-3"
          data-testid="chart-throughput-error"
        >
          <div className="flex items-start gap-2">
            <span
              aria-hidden
              className="material-symbols-outlined text-lg text-destructive"
            >
              error
            </span>
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium text-foreground">
                Không thể tải dữ liệu
              </p>
              <p className="text-xs text-muted-foreground">
                Vui lòng thử lại sau giây lát.
              </p>
            </div>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              data-testid="chart-throughput-retry"
              className="inline-flex h-9 w-fit items-center gap-2 rounded-lg border border-border bg-background px-3 text-xs font-medium text-foreground transition-colors hover:bg-muted"
            >
              <span aria-hidden className="material-symbols-outlined text-base">
                refresh
              </span>
              Thử lại
            </button>
          )}
        </div>
      </article>
    );
  }

  if (loading || data === null) {
    return (
      <article
        data-testid="chart-throughput"
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
        aria-busy="true"
        aria-label="Đang tải biểu đồ số việc hoàn thành"
      >
        <header className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Số việc hoàn thành
          </h3>
          <p className="text-xs text-muted-foreground">
            Nhịp hoàn thành theo từng khoảng thời gian.
          </p>
        </header>
        <div
          className="h-[300px] animate-pulse rounded-lg bg-muted/50"
          data-testid="chart-throughput-skeleton"
          aria-hidden
        />
      </article>
    );
  }

  if (!data.feature_enabled) {
    return (
      <article
        data-testid="chart-throughput"
        className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-card/40 p-4 sm:p-5"
      >
        <h3 className="text-sm font-semibold text-foreground">
          Số việc hoàn thành
        </h3>
        <p
          className="text-xs text-muted-foreground"
          data-testid="chart-throughput-disabled"
        >
          Tính năng chưa được kích hoạt.
        </p>
      </article>
    );
  }

  const series = data.chart_series.throughput_series;
  if (series.length === 0) {
    return (
      <article
        data-testid="chart-throughput"
        className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-card/40 p-4 sm:p-5"
      >
        <h3 className="text-sm font-semibold text-foreground">
          Số việc hoàn thành
        </h3>
        <p
          className="text-xs text-muted-foreground"
          data-testid="chart-throughput-empty"
        >
          Chưa có dữ liệu hoàn thành trong khoảng thời gian này.
        </p>
        {data.as_of && (
          <p className="text-[11px] text-muted-foreground">
            Cập nhật lúc: {formatAsOf(data.as_of)}
          </p>
        )}
      </article>
    );
  }

  const rows = buildChartRows(series);
  const stale = isStale(data.as_of);

  function handleBarClick(entry: { payload?: ChartRow }) {
    const row = entry?.payload;
    if (!row?.period_start || !row?.period_end) return;
    const url =
      "/admin/tasks?completed_from=" +
      encodeURIComponent(row.period_start) +
      "&completed_to=" +
      encodeURIComponent(row.period_end);
    router.push(url);
  }

  return (
    <article
      data-testid="chart-throughput"
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Số việc hoàn thành
          </h3>
          <p className="text-xs text-muted-foreground">
            Số task hoàn thành theo từng khoảng thời gian. Bấm vào cột để xem
            danh sách công việc tương ứng.
          </p>
        </div>
        {stale && (
          <span
            className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-secondary-foreground"
            data-testid="chart-throughput-stale-badge"
            title="Ảnh chụp gần nhất đã quá 24 giờ"
          >
            <span
              aria-hidden
              className="material-symbols-outlined text-[13px] leading-none"
            >
              warning
            </span>
            Dữ liệu có thể cũ
          </span>
        )}
      </header>

      <div
        className="h-[300px] w-full"
        role="img"
        aria-label="Biểu đồ số việc hoàn thành theo khoảng thời gian"
      >
        <ResponsiveContainer width="100%" height={300}>
          <BarChart
            data={rows}
            margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(15,42,42,0.10)"
            />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: "#5F7676" }}
              stroke="rgba(15,42,42,0.10)"
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#5F7676" }}
              stroke="rgba(15,42,42,0.10)"
              allowDecimals={false}
            />
            <Tooltip
              cursor={{ fill: "rgba(45,131,128,0.08)" }}
              content={ThroughputTooltip}
            />
            <Bar
              dataKey="tasks_completed"
              name="Số việc hoàn thành"
              fill={BAR_COLOR}
              radius={[4, 4, 0, 0]}
              cursor="pointer"
              onClick={handleBarClick}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Screen-reader fallback: full data table mirroring the chart so
          assistive tech users can still consume the trend. */}
      <table className="sr-only" data-testid="chart-throughput-table-fallback">
        <caption>
          Bảng dữ liệu số việc hoàn thành theo khoảng thời gian.
        </caption>
        <thead>
          <tr>
            <th scope="col">Khoảng thời gian</th>
            <th scope="col">Số việc hoàn thành</th>
            <th scope="col">Story points</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.period_start}-${row.period_end}`}>
              <th scope="row">
                {formatRangeLabel(row.period_start, row.period_end)}
              </th>
              <td>{row.tasks_completed}</td>
              <td>{row.story_points_completed}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <footer className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span data-testid="chart-throughput-as-of">
          Cập nhật lúc: {formatAsOf(data.as_of)}
        </span>
        <span>{rows.length} khoảng thời gian</span>
      </footer>
    </article>
  );
}
