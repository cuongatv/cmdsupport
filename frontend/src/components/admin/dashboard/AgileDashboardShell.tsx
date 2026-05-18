"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { AgileKpiStrip } from "@/components/admin/dashboard/AgileKpiStrip";
import { AgileCfd } from "@/components/admin/dashboard/AgileCfd";
import { AgileAgingWip } from "@/components/admin/dashboard/AgileAgingWip";
import { AgileThroughput } from "@/components/admin/dashboard/AgileThroughput";
import { AgileBlockedPanel } from "@/components/admin/dashboard/AgileBlockedPanel";
import { AgileCapacityHeatmap } from "@/components/admin/dashboard/AgileCapacityHeatmap";
import {
  getAdminDashboardFlowSummary,
  type AdminDashboardQueryParams,
} from "@/lib/task-api";
import type { AdminDashboardFlowSummaryResponse } from "@/lib/task-types";

type RangeDays = 7 | 14 | 30 | 90;

// Date range presets surfaced by the range filter pill group. Values are
// expressed in days; the shell translates the active value into
// `start_date` / `end_date` ISO strings before calling the API.
const RANGE_OPTIONS: { value: RangeDays; label: string }[] = [
  { value: 7, label: "7 ngày" },
  { value: 14, label: "14 ngày" },
  { value: 30, label: "30 ngày" },
  { value: 90, label: "90 ngày" },
];

function toISODate(value: Date): string {
  return value.toISOString().split("T")[0];
}

function getDateRangeParams(rangeDays: RangeDays): Pick<
  AdminDashboardQueryParams,
  "start_date" | "end_date"
> {
  const today = new Date();
  const start = new Date(today);
  start.setDate(today.getDate() - rangeDays);
  return {
    start_date: toISODate(start),
    end_date: toISODate(today),
  };
}

function cleanFilterParams(
  filters: AdminDashboardQueryParams,
): Omit<
  AdminDashboardQueryParams,
  "start_date" | "end_date"
> {
  const params: Omit<
    AdminDashboardQueryParams,
    "start_date" | "end_date"
  > = {};
  if (filters.department_id) params.department_id = filters.department_id;
  if (filters.workspace_id) params.workspace_id = filters.workspace_id;
  if (filters.project_id) params.project_id = filters.project_id;
  if (filters.sprint_id) params.sprint_id = filters.sprint_id;
  return params;
}

function formatAsOf(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

// Snapshot freshness threshold shared across the dashboard. Mirrors the
// per-widget stale badges in AgileCfd / AgileThroughput so the shell-level
// banner fires on the same boundary.
const STALE_THRESHOLD_MS = 24 * 60 * 60 * 1000;

function isStale(value: string | null | undefined): boolean {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  return Date.now() - date.getTime() > STALE_THRESHOLD_MS;
}

// AgileDashboardShell — Agile view that hosts the filters and the section
// grid. All six section slots (T8–T13) are backed by real API data from the
// admin flow summary endpoint.
export function AgileDashboardShell() {
  const [rangeDays, setRangeDays] = useState<RangeDays>(14);
  const [filters, setFilters] = useState<AdminDashboardQueryParams>({});
  const [refreshKey, setRefreshKey] = useState(0);
  const [dashboardData, setDashboardData] =
    useState<AdminDashboardFlowSummaryResponse | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState(false);

  const dashboardParams = useMemo<AdminDashboardQueryParams>(() => {
    return {
      ...getDateRangeParams(rangeDays),
      ...cleanFilterParams(filters),
    };
  }, [rangeDays, filters]);

  const handleSelectChange =
    (key: keyof AdminDashboardQueryParams) =>
    (event: React.ChangeEvent<HTMLSelectElement>) => {
      const value = event.target.value;
      setFilters((prev) => ({
        ...prev,
        [key]: value === "" ? null : value,
      }));
    };

  useEffect(() => {
    let ignore = false;

    async function loadDashboard() {
      setDashboardLoading(true);
      setDashboardError(false);
      try {
        const data = await getAdminDashboardFlowSummary(dashboardParams);
        if (!ignore) {
          setDashboardData(data);
        }
      } catch {
        if (!ignore) {
          setDashboardError(true);
        }
      } finally {
        if (!ignore) {
          setDashboardLoading(false);
        }
      }
    }

    loadDashboard();

    return () => {
      ignore = true;
    };
  }, [dashboardParams, refreshKey]);

  const handleRefresh = () => {
    setRefreshKey((current) => current + 1);
  };

  return (
    <div
      data-testid="agile-dashboard-root"
      className="flex flex-col gap-6"
    >
      <PageHeader
        title="Tổng quan luồng công việc Agile"
        description="Theo dõi WIP, throughput, aging và tải trọng đội ngũ theo phòng ban, không gian và dự án. Bộ lọc và biểu đồ sẽ được hoàn thiện trong các bước tiếp theo."
      />

      <section
        className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 sm:p-5"
        data-testid="agile-dashboard-filters"
      >
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-foreground">Bộ lọc</h3>
          <p className="text-xs text-muted-foreground">
            Lựa chọn khoảng thời gian và phạm vi cần xem.
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            className="flex flex-wrap items-center gap-2"
            data-testid="dashboard-range-filter"
            role="group"
            aria-label="Khoảng thời gian"
          >
            {RANGE_OPTIONS.map((option) => {
              const isActive = option.value === rangeDays;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setRangeDays(option.value)}
                  data-testid={`dashboard-range-${option.value}d`}
                  aria-pressed={isActive}
                  className={
                    "rounded-full border px-3 py-1 text-xs font-medium transition-colors " +
                    (isActive
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground")
                  }
                >
                  {option.label}
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={handleRefresh}
            data-testid="dashboard-refresh"
            disabled={dashboardLoading}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-border bg-background px-3 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span aria-hidden className="material-symbols-outlined text-base">
              refresh
            </span>
            Làm mới
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <FilterSelect
            label="Phòng ban"
            testId="dashboard-filter-department"
            value={filters.department_id ?? ""}
            onChange={handleSelectChange("department_id")}
            placeholder="Tất cả phòng ban"
          />
          <FilterSelect
            label="Không gian làm việc"
            testId="dashboard-filter-workspace"
            value={filters.workspace_id ?? ""}
            onChange={handleSelectChange("workspace_id")}
            placeholder="Tất cả không gian"
          />
          <FilterSelect
            label="Dự án"
            testId="dashboard-filter-project"
            value={filters.project_id ?? ""}
            onChange={handleSelectChange("project_id")}
            placeholder="Tất cả dự án"
          />
        </div>

        {dashboardData?.as_of && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="dashboard-as-of"
          >
            Cập nhật lúc: {formatAsOf(dashboardData.as_of)}
          </p>
        )}
      </section>

      <Link
        href="/admin/workspaces"
        data-testid="workspace-management-link"
        className="group flex items-center justify-between gap-4 rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-primary/5 sm:p-5"
      >
        <div className="flex items-start gap-3">
          <span
            aria-hidden
            className="material-symbols-outlined mt-0.5 text-2xl text-primary"
          >
            workspaces
          </span>
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-semibold text-foreground">
              Quản lý không gian
            </span>
            <span className="text-xs text-muted-foreground">
              Mở danh sách không gian nghiệp vụ, thành viên và tài liệu.
            </span>
          </div>
        </div>
        <span
          aria-hidden
          className="material-symbols-outlined text-base text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
        >
          arrow_forward
        </span>
      </Link>

      {dashboardData && isStale(dashboardData.as_of) && (
        <section
          data-testid="stale-data-warning"
          role="status"
          className="flex flex-wrap items-start gap-3 rounded-xl border border-amber-400/60 bg-amber-50 p-3 sm:p-4"
        >
          <span
            aria-hidden
            className="material-symbols-outlined text-lg text-amber-700"
          >
            warning
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="text-sm font-semibold text-amber-900">
              Dữ liệu có thể đã cũ
            </p>
            <p className="text-xs text-amber-800">
              Ảnh chụp gần nhất đã quá 24 giờ. Cập nhật lúc:{" "}
              <span data-testid="stale-data-warning-as-of">
                {formatAsOf(dashboardData.as_of)}
              </span>
            </p>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            data-testid="stale-data-warning-refresh"
            className="inline-flex h-8 w-fit items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 text-xs font-medium text-amber-900 transition-colors hover:bg-amber-100"
          >
            <span aria-hidden className="material-symbols-outlined text-sm">
              refresh
            </span>
            Làm mới
          </button>
        </section>
      )}

      <AgileKpiStrip
        data={dashboardData}
        loading={dashboardLoading}
        error={dashboardError}
        onRetry={handleRefresh}
      />

      <div
        className="grid grid-cols-1 gap-4 lg:grid-cols-2"
        data-testid="agile-dashboard-sections"
      >
        <AgileCfd
          data={dashboardData}
          loading={dashboardLoading}
          error={dashboardError}
          onRetry={handleRefresh}
        />
        <AgileAgingWip
          data={dashboardData}
          loading={dashboardLoading}
          error={dashboardError}
          onRetry={handleRefresh}
        />
        <AgileThroughput
          data={dashboardData}
          loading={dashboardLoading}
          error={dashboardError}
          onRetry={handleRefresh}
        />
        <AgileBlockedPanel
          data={dashboardData}
          loading={dashboardLoading}
          error={dashboardError}
          onRetry={handleRefresh}
        />
        <AgileCapacityHeatmap
          data={dashboardData}
          loading={dashboardLoading}
          error={dashboardError}
          onRetry={handleRefresh}
        />
      </div>
    </div>
  );
}

type FilterSelectProps = {
  label: string;
  testId: string;
  value: string;
  onChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  placeholder: string;
};

// Scope option lists are populated in a future task; keep the selects disabled
// while still preserving their state so typed filters flow into the API once
// options are available.
function FilterSelect({
  label,
  testId,
  value,
  onChange,
  placeholder,
}: FilterSelectProps) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
      <span>{label}</span>
      <select
        data-testid={testId}
        value={value}
        onChange={onChange}
        disabled
        className="h-9 w-full rounded-lg border border-border bg-background px-2 text-sm text-foreground disabled:cursor-not-allowed disabled:opacity-70"
      >
        <option value="">{placeholder}</option>
      </select>
    </label>
  );
}
