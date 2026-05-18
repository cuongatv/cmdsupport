"use client";

import Link from "next/link";
import type {
  AdminDashboardFlowSummaryResponse,
  AdminDashboardRiskItem,
} from "@/lib/task-types";

// T10 — Aging WIP risk list for the Agile flow dashboard.
//
// Renders `data.risk_items` as a sorted, drill-down list of tasks that have
// exceeded the project's aging threshold. Each row links into
// `/admin/tasks?task_id=<id>` so a portal admin can pivot from the dashboard
// into the source task with a single click.
//
// Data wiring (`getAdminDashboardFlowSummary`) lives in T14. The shell
// currently passes `data={null}` so we treat null as "parent has not loaded
// yet" and render the skeleton list to keep the layout stable.

type AgileAgingWipProps = {
  data: AdminDashboardFlowSummaryResponse | null;
  loading: boolean;
};

// Maximum rows rendered before we collapse the tail into a "+N khác" hint.
// 10 keeps the section roughly the same height as the CFD slot beside it.
const MAX_VISIBLE_ROWS = 10;

// Severity buckets emitted by the backend (`app/schemas/tasks.py`
// `AdminDashboardRiskItem.severity`). The string is informational, so we
// normalise to lower-case and map to a visual tier:
//   - `critical` / `high` / `blocked` -> destructive (red)
//   - `medium` / `warning` -> amber warning
//   - everything else -> muted neutral
type SeverityTier = "danger" | "warning" | "neutral";

const DANGER_SEVERITIES = new Set([
  "critical",
  "high",
  "danger",
  "blocked",
  "overdue",
]);

const WARNING_SEVERITIES = new Set(["medium", "warning", "warn", "aging"]);

function severityTier(severity: string | null | undefined): SeverityTier {
  const normalised = (severity ?? "").trim().toLowerCase();
  if (DANGER_SEVERITIES.has(normalised)) return "danger";
  if (WARNING_SEVERITIES.has(normalised)) return "warning";
  return "neutral";
}

function severityLabel(tier: SeverityTier): string {
  if (tier === "danger") return "Nguy cấp";
  if (tier === "warning") return "Cảnh báo";
  return "Theo dõi";
}

// Tailwind class bundles per tier. Kept inline (vs. a lookup object that
// would be tree-shaken away) so the static class strings survive Tailwind 4
// JIT scanning.
function rowAccentClass(tier: SeverityTier): string {
  if (tier === "danger") {
    return "border-l-destructive bg-destructive/5";
  }
  if (tier === "warning") {
    return "border-l-amber-500 bg-amber-50/60";
  }
  return "border-l-border bg-card";
}

function badgeClass(tier: SeverityTier): string {
  if (tier === "danger") {
    return "bg-destructive/10 text-destructive";
  }
  if (tier === "warning") {
    return "bg-amber-100 text-amber-700";
  }
  return "bg-muted text-muted-foreground";
}

function ageClass(tier: SeverityTier): string {
  if (tier === "danger") return "text-destructive";
  if (tier === "warning") return "text-amber-700";
  return "text-muted-foreground";
}

function sortByAgeDesc(
  items: readonly AdminDashboardRiskItem[],
): AdminDashboardRiskItem[] {
  // Oldest-first per the T10 spec. `count` is the aging-day proxy emitted by
  // the backend (`AdminDashboardRiskItem.count`); ties fall back to title so
  // the order stays deterministic across re-renders.
  return [...items].sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.title.localeCompare(b.title, "vi");
  });
}

export function AgileAgingWip({ data, loading }: AgileAgingWipProps) {
  const showSkeleton = loading || data === null;

  if (showSkeleton) {
    return (
      <article
        data-testid="chart-aging-wip"
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
        aria-busy="true"
        aria-label="Đang tải danh sách công việc tồn lâu"
      >
        <header className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Công việc tồn lâu
          </h3>
          <p className="text-xs text-muted-foreground">
            Danh sách task vượt ngưỡng tuổi theo trạng thái.
          </p>
        </header>
        <ul
          className="flex flex-col gap-2"
          data-testid="aging-risk-list-skeleton"
        >
          {Array.from({ length: 4 }).map((_, idx) => (
            <li
              key={idx}
              className="h-14 animate-pulse rounded-lg bg-muted/50"
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
        data-testid="chart-aging-wip"
        className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-card/40 p-4 sm:p-5"
      >
        <h3 className="text-sm font-semibold text-foreground">
          Công việc tồn lâu
        </h3>
        <p
          className="text-xs text-muted-foreground"
          data-testid="aging-risk-list-disabled"
        >
          Tính năng chưa được kích hoạt
        </p>
      </article>
    );
  }

  const sorted = sortByAgeDesc(data.risk_items);
  const visible = sorted.slice(0, MAX_VISIBLE_ROWS);
  const hiddenCount = Math.max(0, sorted.length - visible.length);

  return (
    <article
      data-testid="chart-aging-wip"
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Công việc tồn lâu
          </h3>
          <p className="text-xs text-muted-foreground">
            Sắp xếp theo số ngày tồn nhiều nhất.
          </p>
        </div>
        <Link
          href="/admin/tasks?aging=true"
          data-testid="aging-risk-list-view-all"
          className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
        >
          <span
            aria-hidden
            className="material-symbols-outlined text-[13px] leading-none"
          >
            hourglass_top
          </span>
          Xem tất cả
        </Link>
      </header>

      {sorted.length === 0 ? (
        <p
          className="rounded-lg border border-dashed border-border bg-muted/30 px-3 py-6 text-center text-xs text-muted-foreground"
          data-testid="aging-risk-list-empty"
        >
          Không có công việc nào tồn lâu.
        </p>
      ) : (
        <>
          <ul
            data-testid="aging-risk-list"
            className="flex flex-col gap-2"
          >
            {visible.map((item) => (
              <AgingRow key={item.id} item={item} />
            ))}
          </ul>
          {hiddenCount > 0 && (
            <p
              className="text-[11px] text-muted-foreground"
              data-testid="aging-risk-list-hidden-count"
            >
              + {hiddenCount} công việc khác đang chờ rà soát
            </p>
          )}
        </>
      )}
    </article>
  );
}

type AgingRowProps = {
  item: AdminDashboardRiskItem;
};

function AgingRow({ item }: AgingRowProps) {
  const tier = severityTier(item.severity);
  const accent = rowAccentClass(tier);
  const badge = badgeClass(tier);
  const age = ageClass(tier);

  return (
    <li>
      <Link
        href={`/admin/tasks?task_id=${encodeURIComponent(item.id)}`}
        data-testid={`aging-risk-item-${item.id}`}
        className={`group flex items-start justify-between gap-3 rounded-lg border border-border border-l-4 px-3 py-2.5 transition-colors hover:border-primary/40 hover:bg-primary/5 ${accent}`}
      >
        <div className="flex min-w-0 flex-col gap-1">
          <span className="truncate text-sm font-medium text-foreground">
            {item.title}
          </span>
          {item.description && (
            <span className="line-clamp-2 text-xs text-muted-foreground">
              {item.description}
            </span>
          )}
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${badge}`}
              data-testid={`aging-risk-item-${item.id}-severity`}
            >
              {severityLabel(tier)}
            </span>
            {tier === "danger" && (
              <span
                className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
                data-testid={`aging-risk-item-${item.id}-blocked`}
              >
                <span
                  aria-hidden
                  className="material-symbols-outlined text-[13px] leading-none"
                >
                  block
                </span>
                Đang bị chặn
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1 pl-2">
          <span
            className={`text-sm font-semibold tabular-nums ${age}`}
            data-testid={`aging-risk-item-${item.id}-age`}
          >
            {item.count} ngày
          </span>
          <span
            aria-hidden
            className="material-symbols-outlined text-base text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
          >
            arrow_forward
          </span>
        </div>
      </Link>
    </li>
  );
}
