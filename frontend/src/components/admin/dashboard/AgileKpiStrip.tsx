"use client";

import Link from "next/link";
import type { AdminDashboardFlowSummaryResponse } from "@/lib/task-types";

// T8 — KPI strip for the Agile flow dashboard. Six metric cards covering
// WIP, blocked, aging, throughput, cycle time and lead time. The component
// renders three distinct empty / disabled / loading states explicitly so
// users never see silent zeros while Phase 5 is off or while data is in
// flight.
//
// Data wiring (`getAdminDashboardFlowSummary`) is intentionally NOT done
// here — that lives in T14. The shell currently passes `data={null}` so
// we treat null as "parent has not loaded yet" and render the skeleton
// row to keep the layout stable.

type AgileKpiStripProps = {
  data: AdminDashboardFlowSummaryResponse | null;
  loading: boolean;
  error?: boolean;
  onRetry?: () => void;
};

type KpiEntry = {
  testId: string;
  label: string;
  icon: string;
  value: string;
  href?: string;
  approximated?: boolean;
};

const APPROXIMATION_TOOLTIP =
  "Thời gian chu kỳ và chờ được tính xấp xỉ do thiếu dữ liệu lịch sử chính xác.";

function formatDays(value: number): string {
  // Backend emits cycle/lead time as floats in days. Render with one
  // decimal so sub-day differences stay visible without ballooning card
  // width; fall back to em-dash for non-finite values (e.g. 0/0).
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(1)} ngày`;
}

export function AgileKpiStrip({
  data,
  loading,
  error = false,
  onRetry,
}: AgileKpiStripProps) {
  const showError = error && data === null && !loading;

  if (showError) {
    return (
      <section
        className="flex flex-col gap-3 rounded-xl border border-destructive/30 bg-card p-4 sm:p-5"
        data-testid="agile-kpi-strip-error"
      >
        <div className="flex items-start gap-3">
          <span
            aria-hidden
            className="material-symbols-outlined text-xl text-destructive"
          >
            error
          </span>
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-foreground">
              Không thể tải dữ liệu
            </h3>
            <p className="text-xs text-muted-foreground">
              Vui lòng thử lại sau giây lát.
            </p>
          </div>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            data-testid="agile-kpi-strip-retry"
            className="inline-flex h-9 w-fit items-center gap-2 rounded-lg border border-border bg-background px-3 text-xs font-medium text-foreground transition-colors hover:bg-muted"
          >
            <span aria-hidden className="material-symbols-outlined text-base">
              refresh
            </span>
            Thử lại
          </button>
        )}
      </section>
    );
  }

  if (loading || data === null) {
    return (
      <section
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6"
        data-testid="agile-kpi-strip-loading"
        aria-busy="true"
        aria-label="Đang tải KPI dòng chảy"
      >
        {Array.from({ length: 6 }).map((_, idx) => (
          <div
            key={idx}
            className="h-28 animate-pulse rounded-xl bg-muted/50"
            data-testid={`kpi-skeleton-${idx}`}
            aria-hidden
          />
        ))}
      </section>
    );
  }

  if (!data.feature_enabled) {
    return (
      <section
        className="flex items-start gap-4 rounded-xl border border-dashed border-border bg-card/40 p-5"
        data-testid="agile-kpi-strip-disabled"
      >
        <span
          aria-hidden
          className="material-symbols-outlined mt-0.5 text-3xl text-muted-foreground"
        >
          toggle_off
        </span>
        <div className="flex flex-col gap-1">
          <h3 className="text-base font-semibold text-foreground">
            Tính năng Agile chưa được kích hoạt
          </h3>
          <p className="text-sm text-muted-foreground">
            Liên hệ quản trị viên để bật Phase 5.
          </p>
        </div>
      </section>
    );
  }

  if (data.scoped_project_count === 0) {
    return (
      <section
        className="flex items-center gap-3 rounded-xl border border-dashed border-border bg-card/40 p-5"
        data-testid="agile-kpi-strip-empty"
      >
        <span
          aria-hidden
          className="material-symbols-outlined text-2xl text-muted-foreground"
        >
          folder_off
        </span>
        <p className="text-sm text-muted-foreground">
          Không có dự án nào trong phạm vi của bạn.
        </p>
      </section>
    );
  }

  const entries: KpiEntry[] = [
    {
      testId: "kpi-wip",
      label: "Đang thực hiện",
      icon: "inventory_2",
      value: String(data.wip_count),
    },
    {
      testId: "kpi-blocked",
      label: "Đang bị chặn",
      icon: "block",
      value: String(data.blocked_count),
      href: "/admin/tasks?blocked=true",
    },
    {
      testId: "kpi-aging",
      label: "Tồn lâu",
      icon: "hourglass_top",
      value: String(data.aging_count),
      href: "/admin/tasks?aging=true",
    },
    {
      testId: "kpi-throughput",
      label: "Hoàn thành",
      icon: "check_circle",
      value: String(data.throughput_count),
    },
    {
      testId: "kpi-cycle-time",
      label: "Thời gian chu kỳ (P50)",
      icon: "timer",
      value: formatDays(data.cycle_time_p50),
      approximated: data.approximation_used,
    },
    {
      testId: "kpi-lead-time",
      label: "Thời gian chờ (P50)",
      icon: "schedule",
      value: formatDays(data.lead_time_p50),
      approximated: data.approximation_used,
    },
  ];

  return (
    <section
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6"
      data-testid="agile-kpi-strip"
    >
      {entries.map((entry) => (
        <KpiCard key={entry.testId} entry={entry} />
      ))}
    </section>
  );
}

type KpiCardProps = {
  entry: KpiEntry;
};

function KpiCard({ entry }: KpiCardProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {entry.label}
        </span>
        <span
          aria-hidden
          className="material-symbols-outlined text-xl text-primary"
        >
          {entry.icon}
        </span>
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
        {entry.value}
      </div>
      {entry.approximated && (
        <span
          className="mt-2 inline-flex w-fit items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-secondary-foreground"
          title={APPROXIMATION_TOOLTIP}
          data-testid={`${entry.testId}-approximation-badge`}
        >
          <span
            aria-hidden
            className="material-symbols-outlined text-[13px] leading-none"
          >
            info
          </span>
          Số liệu xấp xỉ
        </span>
      )}
    </>
  );

  const baseClass =
    "flex flex-col rounded-xl border border-border bg-card p-4 transition-colors";

  if (entry.href) {
    return (
      <Link
        href={entry.href}
        data-testid={entry.testId}
        className={`${baseClass} hover:border-primary/40 hover:bg-primary/5`}
      >
        {body}
      </Link>
    );
  }

  return (
    <div data-testid={entry.testId} className={baseClass}>
      {body}
    </div>
  );
}
