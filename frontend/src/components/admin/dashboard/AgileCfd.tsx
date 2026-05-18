"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  AdminDashboardFlowSummaryResponse,
  CfdDataPoint,
} from "@/lib/task-types";

// T9 — Cumulative Flow Diagram for the Agile dashboard.
//
// Renders `chart_series.cfd_series` as a stacked area chart, one stack per
// state group (todo / in_progress / done / cancelled / fallback). All
// user-facing strings are hardcoded Vietnamese per the project-wide
// decision not to introduce an i18n framework.
//
// Data wiring lives in T14: this component is purely presentational and
// takes the dashboard payload via props so the shell can mount it with
// `data={null}` until the fetch is plumbed.

type AgileCfdProps = {
  data: AdminDashboardFlowSummaryResponse | null;
  loading: boolean;
};

// Vietnamese labels for the well-known state groups. Unmapped groups
// (the backend lets projects define custom state.group values) fall back
// to the raw key so the legend never goes blank.
const GROUP_LABELS: Record<string, string> = {
  todo: "Chờ xử lý",
  in_progress: "Đang làm",
  done: "Hoàn thành",
  cancelled: "Đã hủy",
};

// Color tokens come from globals.css / DESIGN.md. Hard-coded hex values
// (rather than CSS variables) because Recharts paints into SVG `fill` /
// `stroke` attributes that do not resolve `var(--token)` reliably across
// browsers. The palette below stays inside the BIDV chart-1..chart-5
// scale plus the DESIGN.md warning amber for in-progress emphasis.
const GROUP_COLORS: Record<string, string> = {
  todo: "#5F7676", // chart-5 — muted slate (waiting)
  in_progress: "#E0A23B", // DESIGN.md warning amber (active work)
  done: "#2D8380", // chart-3 / BIDV primary teal (completed)
  cancelled: "#C0392B", // destructive (cancelled)
};

const FALLBACK_COLOR = "#7BC9C0"; // chart-4 — neutral teal

const STALE_THRESHOLD_MS = 24 * 60 * 60 * 1000;

// Preferred render order so the stack reads left-to-right "queue ->
// active -> done" without shuffling between renders.
const PREFERRED_GROUP_ORDER = ["todo", "in_progress", "done", "cancelled"];

function vietnameseGroupLabel(group: string): string {
  return GROUP_LABELS[group] ?? group;
}

function groupColor(group: string): string {
  return GROUP_COLORS[group] ?? FALLBACK_COLOR;
}

function formatAsOf(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatChartDate(value: string): string {
  // Snapshot dates come in as `YYYY-MM-DD`. Render `DD/MM` on the axis so
  // 14- and 30-day ranges stay readable without rotating ticks.
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function isStale(asOf: string): boolean {
  const date = new Date(asOf);
  if (Number.isNaN(date.getTime())) return false;
  return Date.now() - date.getTime() > STALE_THRESHOLD_MS;
}

type ChartRow = { date: string } & Record<string, string | number>;

function buildChartRows(series: CfdDataPoint[]): {
  rows: ChartRow[];
  groups: string[];
} {
  // Collect every distinct state-group key across the window so custom
  // project groups still render even when they appear only on a subset
  // of snapshots.
  const groupSet = new Set<string>();
  for (const point of series) {
    for (const key of Object.keys(point.state_counts)) {
      groupSet.add(key);
    }
  }

  const seen = new Set<string>();
  const groups: string[] = [];
  for (const key of PREFERRED_GROUP_ORDER) {
    if (groupSet.has(key)) {
      groups.push(key);
      seen.add(key);
    }
  }
  for (const key of Array.from(groupSet).sort()) {
    if (!seen.has(key)) {
      groups.push(key);
    }
  }

  const rows: ChartRow[] = series
    .slice()
    .sort((a, b) => (a.snapshot_date < b.snapshot_date ? -1 : 1))
    .map((point) => {
      const row: ChartRow = { date: formatChartDate(point.snapshot_date) };
      for (const group of groups) {
        row[group] = point.state_counts[group] ?? 0;
      }
      return row;
    });

  return { rows, groups };
}

export function AgileCfd({ data, loading }: AgileCfdProps) {
  const showSkeleton = loading || data === null;

  if (showSkeleton) {
    return (
      <article
        data-testid="chart-cfd"
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
        aria-busy="true"
        aria-label="Đang tải biểu đồ tích lũy"
      >
        <header className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Cumulative Flow Diagram
          </h3>
          <p className="text-xs text-muted-foreground">
            Biểu đồ tích lũy theo trạng thái theo thời gian.
          </p>
        </header>
        <div
          className="h-[300px] animate-pulse rounded-lg bg-muted/50"
          data-testid="chart-cfd-skeleton"
          aria-hidden
        />
      </article>
    );
  }

  if (!data.feature_enabled) {
    return (
      <article
        data-testid="chart-cfd"
        className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-card/40 p-4 sm:p-5"
      >
        <h3 className="text-sm font-semibold text-foreground">
          Cumulative Flow Diagram
        </h3>
        <p
          className="text-xs text-muted-foreground"
          data-testid="chart-cfd-disabled"
        >
          Tính năng chưa được kích hoạt
        </p>
      </article>
    );
  }

  const series = data.chart_series.cfd_series;
  if (series.length < 2) {
    return (
      <article
        data-testid="chart-cfd"
        className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-card/40 p-4 sm:p-5"
      >
        <h3 className="text-sm font-semibold text-foreground">
          Cumulative Flow Diagram
        </h3>
        <p
          className="text-xs text-muted-foreground"
          data-testid="chart-cfd-empty"
        >
          Chưa đủ dữ liệu để vẽ biểu đồ. Cần ít nhất 2 ngày dữ liệu.
        </p>
        {data.as_of && (
          <p className="text-[11px] text-muted-foreground">
            Cập nhật lúc: {formatAsOf(data.as_of)}
          </p>
        )}
      </article>
    );
  }

  const { rows, groups } = buildChartRows(series);
  const stale = isStale(data.as_of);

  return (
    <article
      data-testid="chart-cfd"
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Cumulative Flow Diagram
          </h3>
          <p className="text-xs text-muted-foreground">
            Tổng số công việc theo nhóm trạng thái mỗi ngày.
          </p>
        </div>
        {stale && (
          <span
            className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-secondary-foreground"
            data-testid="chart-cfd-stale-badge"
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
        aria-label="Biểu đồ tích lũy công việc theo nhóm trạng thái"
      >
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart
            data={rows}
            margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(15,42,42,0.10)"
            />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "#5F7676" }}
              stroke="rgba(15,42,42,0.10)"
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#5F7676" }}
              stroke="rgba(15,42,42,0.10)"
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                background: "#FFFFFF",
                border: "1px solid rgba(15,42,42,0.10)",
                borderRadius: 10,
                fontSize: 12,
              }}
              labelStyle={{ color: "#0F2A2A", fontWeight: 600 }}
              formatter={(value, name) => [
                typeof value === "number" ? value : String(value ?? ""),
                vietnameseGroupLabel(String(name)),
              ]}
            />
            <Legend
              wrapperStyle={{ fontSize: 12 }}
              formatter={(value: string) => vietnameseGroupLabel(value)}
            />
            {groups.map((group) => (
              <Area
                key={group}
                type="monotone"
                dataKey={group}
                stackId="cfd"
                stroke={groupColor(group)}
                fill={groupColor(group)}
                fillOpacity={0.65}
                name={group}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Screen-reader fallback: full data table mirroring the chart so
          assistive tech users can still consume the trend. */}
      <table className="sr-only" data-testid="chart-cfd-table-fallback">
        <caption>
          Bảng dữ liệu Cumulative Flow Diagram theo ngày và nhóm trạng thái.
        </caption>
        <thead>
          <tr>
            <th scope="col">Ngày</th>
            {groups.map((group) => (
              <th scope="col" key={group}>
                {vietnameseGroupLabel(group)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`${row.date}-${idx}`}>
              <th scope="row">{row.date}</th>
              {groups.map((group) => (
                <td key={group}>{row[group]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <footer className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span data-testid="chart-cfd-as-of">
          Cập nhật lúc: {formatAsOf(data.as_of)}
        </span>
        <span>{rows.length} ngày dữ liệu</span>
      </footer>
    </article>
  );
}
