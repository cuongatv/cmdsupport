"use client";

import Link from "next/link";
import type {
  AdminDashboardFlowSummaryResponse,
  AdminDashboardRiskItem,
} from "@/lib/task-types";

// T12 — Blocked / risk panel for the Agile flow dashboard.
//
// Renders `data.risk_items` as a severity-sorted list of blockers and risk
// signals. Each row exposes title, severity badge, optional description, and
// the blocked-task count emitted by the backend (`AdminDashboardRiskItem.count`).
// The header "Xem tất cả" link drills into `/admin/tasks?blocked=true` so an
// admin can pivot from the dashboard into the filtered task table.
//
// Data wiring (`getAdminDashboardFlowSummary`) lives in T14. The shell mounts
// this with `data={null}` for now, which we treat as "parent has not loaded
// yet" and render a skeleton list to keep the layout stable.

type AgileBlockedPanelProps = {
  data: AdminDashboardFlowSummaryResponse | null;
  loading: boolean;
  error?: boolean;
  onRetry?: () => void;
};

// Maximum rows rendered before we collapse the tail into a "+N khác" hint.
// 8 keeps this panel shorter than the Aging list it sits beside so blockers
// stay scannable at a glance.
const MAX_VISIBLE_ROWS = 8;

// Severity buckets emitted by the backend (`app/schemas/tasks.py`
// `AdminDashboardRiskItem.severity`). The string is informational, so we
// normalise to lower-case and map to a visual tier:
//   - `critical` / `high` / `danger` / `blocked` / `overdue` -> destructive (red)
//   - `medium` / `warning` / `warn` / `aging` -> amber warning
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
  if (tier === "danger") return "Nghiêm trọng";
  if (tier === "warning") return "Cảnh báo";
  return "Theo dõi";
}

// Sort key per tier: danger first, then warning, then neutral. Stable
// secondary sort by `count` desc keeps the loudest blockers at the top.
const TIER_RANK: Record<SeverityTier, number> = {
  danger: 0,
  warning: 1,
  neutral: 2,
};

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

function countClass(tier: SeverityTier): string {
  if (tier === "danger") return "text-destructive";
  if (tier === "warning") return "text-amber-700";
  return "text-muted-foreground";
}

function sortByTierThenCount(
  items: readonly AdminDashboardRiskItem[],
): AdminDashboardRiskItem[] {
  return [...items].sort((a, b) => {
    const tierDiff = TIER_RANK[severityTier(a.severity)] - TIER_RANK[severityTier(b.severity)];
    if (tierDiff !== 0) return tierDiff;
    if (b.count !== a.count) return b.count - a.count;
    return a.title.localeCompare(b.title, "vi");
  });
}

export function AgileBlockedPanel({
  data,
  loading,
  error = false,
  onRetry,
}: AgileBlockedPanelProps) {
  const showError = error && data === null && !loading;

  if (showError) {
    return (
      <article
        data-testid="risk-panel"
        className="flex flex-col gap-3 rounded-xl border border-destructive/30 bg-card p-4 sm:p-5"
      >
        <header className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Blocker và rủi ro
          </h3>
        </header>
        <div
          className="flex flex-col gap-3 rounded-lg bg-destructive/5 p-3"
          data-testid="blocked-risk-panel-error"
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
              data-testid="blocked-risk-panel-retry"
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
        data-testid="risk-panel"
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
        aria-busy="true"
        aria-label="Đang tải danh sách blocker và rủi ro"
      >
        <header className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Blocker và rủi ro
          </h3>
          <p className="text-xs text-muted-foreground">
            Danh sách công việc đang bị chặn hoặc cần xử lý gấp.
          </p>
        </header>
        <ul
          className="flex flex-col gap-2"
          data-testid="blocked-risk-list-skeleton"
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
        data-testid="risk-panel"
        className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-card/40 p-4 sm:p-5"
      >
        <h3 className="text-sm font-semibold text-foreground">
          Blocker và rủi ro
        </h3>
        <p
          className="text-xs text-muted-foreground"
          data-testid="blocked-risk-list-disabled"
        >
          Tính năng chưa được kích hoạt.
        </p>
      </article>
    );
  }

  const sorted = sortByTierThenCount(data.risk_items);
  const visible = sorted.slice(0, MAX_VISIBLE_ROWS);
  const hiddenCount = Math.max(0, sorted.length - visible.length);

  return (
    <article
      data-testid="risk-panel"
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:p-5"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-foreground">
            Blocker và rủi ro
          </h3>
          <p className="text-xs text-muted-foreground">
            Sắp xếp theo mức độ nghiêm trọng, sau đó tới số lượng công việc.
          </p>
        </div>
        <Link
          href="/admin/tasks?blocked=true"
          data-testid="blocked-risk-list-view-all"
          className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
        >
          <span
            aria-hidden
            className="material-symbols-outlined text-[13px] leading-none"
          >
            block
          </span>
          Xem tất cả
        </Link>
      </header>

      {sorted.length === 0 ? (
        <p
          className="rounded-lg border border-dashed border-border bg-muted/30 px-3 py-6 text-center text-xs text-muted-foreground"
          data-testid="blocked-risk-list-empty"
        >
          Không có rủi ro hoặc blocker nào được ghi nhận.
        </p>
      ) : (
        <>
          <ul
            data-testid="blocked-risk-list"
            className="flex flex-col gap-2"
          >
            {visible.map((item) => (
              <BlockedRow key={item.id} item={item} />
            ))}
          </ul>
          {hiddenCount > 0 && (
            <p
              className="text-[11px] text-muted-foreground"
              data-testid="blocked-risk-list-hidden-count"
            >
              + {hiddenCount} mục khác đang chờ rà soát
            </p>
          )}
        </>
      )}
    </article>
  );
}

type BlockedRowProps = {
  item: AdminDashboardRiskItem;
};

function BlockedRow({ item }: BlockedRowProps) {
  const tier = severityTier(item.severity);
  const accent = rowAccentClass(tier);
  const badge = badgeClass(tier);
  const count = countClass(tier);

  return (
    <li
      data-testid={`blocked-risk-item-${item.id}`}
      className={`flex items-start justify-between gap-3 rounded-lg border border-border border-l-4 px-3 py-2.5 ${accent}`}
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
            data-testid={`blocked-risk-item-${item.id}-severity`}
          >
            {severityLabel(tier)}
          </span>
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1 pl-2">
        <span
          className={`text-sm font-semibold tabular-nums ${count}`}
          data-testid={`blocked-risk-item-${item.id}-count`}
        >
          {item.count}
        </span>
        <span className="text-[11px] text-muted-foreground">công việc</span>
      </div>
    </li>
  );
}
