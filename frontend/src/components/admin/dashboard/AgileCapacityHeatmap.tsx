"use client";

import type {
  AdminDashboardCapacityItem,
  AdminDashboardFlowSummaryResponse,
} from "@/lib/task-types";

// T13 — Capacity heatmap for the Agile flow dashboard.
//
// Renders `data.capacity_items` as a sorted list of capacity bars per squad
// or department. Each row shows: label, horizontal bar (width =
// `capacity_percent` clamped to 100%, fill colour by `is_overloaded`), open
// task count, and a destructive "Quá tải" badge for overloaded entries.
//
// Sorting: overloaded entries float to the top, then by `capacity_percent`
// descending so the busiest squads sit above slack ones. `null` capacity
// (unconfigured) sinks to the bottom and renders a "Chưa cấu hình" hint
// instead of a progress bar.
//
// Data wiring (`getAdminDashboardFlowSummary`) lives in T14. Until then the
// shell mounts this with `data={null}`, which we treat as "parent has not
// loaded yet" and render a skeleton so the layout stays stable.

type AgileCapacityHeatmapProps = {
  data: AdminDashboardFlowSummaryResponse | null;
  loading: boolean;
};

function clampPercent(value: number | null): number {
  if (value === null || Number.isNaN(value)) return 0;
  if (value < 0) return 0;
  if (value > 100) return 100;
  return value;
}

function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  // Round to nearest integer to keep the row visually compact; capacity is
  // already an approximation so sub-percent precision adds noise.
  return `${Math.round(value)}%`;
}

function sortByOverloadThenCapacity(
  items: readonly AdminDashboardCapacityItem[],
): AdminDashboardCapacityItem[] {
  return [...items].sort((a, b) => {
    if (a.is_overloaded !== b.is_overloaded) {
      return a.is_overloaded ? -1 : 1;
    }
    const aValue = a.capacity_percent ?? -1;
    const bValue = b.capacity_percent ?? -1;
    if (bValue !== aValue) return bValue - aValue;
    return a.label.localeCompare(b.label, "vi");
  });
}

export function AgileCapacityHeatmap({
  data,
  loading,
}: AgileCapacityHeatmapProps) {
  const showSkeleton = loading || data === null;

  if (showSkeleton) {
    return (
      <article
        data-testid="capacity-heatmap"
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
        aria-busy="true"
        aria-label="Đang tải biểu đồ tải trọng đội ngũ"
      >
        <header className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Tải trọng đội ngũ
          </h3>
          <p className="text-xs text-muted-foreground">
            Capacity theo squad / phòng ban.
          </p>
        </header>
        <ul
          className="flex flex-col gap-2"
          data-testid="capacity-heatmap-skeleton"
        >
          {Array.from({ length: 5 }).map((_, idx) => (
            <li
              key={idx}
              className="h-12 animate-pulse rounded-lg bg-muted/50"
              aria-hidden
            />
          ))}
        </ul>
      </article>
    );
  }

  if (!data.feature_enabled) {
    return (
      <article
        data-testid="capacity-heatmap"
        className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-card/40 p-4 sm:p-5"
      >
        <h3 className="text-sm font-semibold text-foreground">
          Tải trọng đội ngũ
        </h3>
        <p
          className="text-xs text-muted-foreground"
          data-testid="capacity-heatmap-disabled"
        >
          Tính năng chưa được kích hoạt.
        </p>
      </article>
    );
  }

  const sorted = sortByOverloadThenCapacity(data.capacity_items);

  return (
    <article
      data-testid="capacity-heatmap"
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
    >
      <header className="flex flex-col gap-0.5">
        <h3 className="text-sm font-semibold text-foreground">
          Tải trọng đội ngũ
        </h3>
        <p className="text-xs text-muted-foreground">
          Sắp xếp ưu tiên các squad đang quá tải, sau đó theo capacity giảm dần.
        </p>
      </header>

      {sorted.length === 0 ? (
        <p
          className="rounded-lg border border-dashed border-border bg-muted/30 px-3 py-6 text-center text-xs text-muted-foreground"
          data-testid="capacity-heatmap-empty"
        >
          Chưa có dữ liệu tải trọng đội ngũ.
        </p>
      ) : (
        <ul
          data-testid="capacity-heatmap-list"
          className="flex flex-col gap-2"
        >
          {sorted.map((item) => (
            <CapacityRow key={item.id} item={item} />
          ))}
        </ul>
      )}
    </article>
  );
}

type CapacityRowProps = {
  item: AdminDashboardCapacityItem;
};

function CapacityRow({ item }: CapacityRowProps) {
  const unconfigured = item.capacity_percent === null;
  const width = clampPercent(item.capacity_percent);
  const barFillClass = item.is_overloaded ? "bg-destructive" : "bg-primary";
  const containerAccent = item.is_overloaded
    ? "border-l-destructive bg-destructive/5"
    : "border-l-primary/40 bg-card";

  return (
    <li
      data-testid={`capacity-heatmap-item-${item.id}`}
      className={`flex flex-col gap-2 rounded-lg border border-border border-l-4 px-3 py-2.5 ${containerAccent}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-medium text-foreground">
            {item.label}
          </span>
          {item.is_overloaded && (
            <span
              data-testid={`capacity-heatmap-item-${item.id}-overloaded`}
              className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
            >
              Quá tải
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-3 text-xs">
          <span
            className={`tabular-nums font-semibold ${
              item.is_overloaded ? "text-destructive" : "text-foreground"
            }`}
            data-testid={`capacity-heatmap-item-${item.id}-percent`}
          >
            {formatPercent(item.capacity_percent)}
          </span>
          <span
            className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
            data-testid={`capacity-heatmap-item-${item.id}-tasks`}
          >
            <span aria-hidden className="material-symbols-outlined text-[13px] leading-none">
              checklist
            </span>
            {item.open_task_count} công việc
          </span>
        </div>
      </div>

      {unconfigured ? (
        <p
          className="text-[11px] italic text-muted-foreground"
          data-testid={`capacity-heatmap-item-${item.id}-unconfigured`}
        >
          Chưa cấu hình
        </p>
      ) : (
        <div
          className="relative h-2 w-full overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={Math.round(item.capacity_percent ?? 0)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Capacity ${item.label}`}
          data-testid={`capacity-heatmap-item-${item.id}-bar`}
        >
          <div
            className={`h-full rounded-full ${barFillClass} transition-[width]`}
            style={{ width: `${width}%` }}
          />
        </div>
      )}
    </li>
  );
}
