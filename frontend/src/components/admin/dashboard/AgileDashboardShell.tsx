"use client";

import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { AgileKpiStrip } from "@/components/admin/dashboard/AgileKpiStrip";
import { AgileCfd } from "@/components/admin/dashboard/AgileCfd";
import type { AdminDashboardQueryParams } from "@/lib/task-api";

// Date range presets surfaced by the range filter pill group. Values are
// expressed in days; the data wiring task (T14) translates the active value
// into `start_date` / `end_date` ISO strings before calling the API.
const RANGE_OPTIONS: { value: 7 | 14 | 30 | 90; label: string }[] = [
  { value: 7, label: "7 ngày" },
  { value: 14, label: "14 ngày" },
  { value: 30, label: "30 ngày" },
  { value: 90, label: "90 ngày" },
];

// Placeholder section cards that occupy the slots filled in T10–T13 by the
// aging table, throughput chart, blocked panel, and capacity heatmap. The
// KPI slot (T8) is backed by <AgileKpiStrip> and the CFD slot (T9) by
// <AgileCfd>; data wiring still lives in T14, so both receive `data={null}`
// for now and self-render skeletons.
const PLACEHOLDER_SECTIONS: {
  id: string;
  title: string;
  description: string;
  testId: string;
}[] = [
  {
    id: "aging",
    title: "Công việc tồn lâu",
    description:
      "Danh sách task aging theo trạng thái — sẽ hiển thị ở Wave 2 (T10).",
    testId: "agile-section-aging-placeholder",
  },
  {
    id: "throughput",
    title: "Throughput",
    description:
      "Nhịp hoàn thành theo tuần — sẽ hiển thị ở Wave 2 (T11).",
    testId: "agile-section-throughput-placeholder",
  },
  {
    id: "blocked",
    title: "Công việc đang bị chặn",
    description:
      "Tổng hợp blocker với lý do và người phụ trách — sẽ hiển thị ở Wave 2 (T12).",
    testId: "agile-section-blocked-placeholder",
  },
  {
    id: "capacity",
    title: "Tải trọng đội ngũ",
    description:
      "Heatmap capacity theo squad/phòng ban — sẽ hiển thị ở Wave 2 (T13).",
    testId: "agile-section-capacity-placeholder",
  },
];

// AgileDashboardShell — empty Agile view that hosts the filters and the
// section skeleton until T8–T14 fill in the charts and data wiring.
// Filter state is intentionally local: this task only renders the controls;
// `getAdminDashboardFlowSummary` is not called yet (deferred to T14).
export function AgileDashboardShell() {
  const [rangeDays, setRangeDays] = useState<7 | 14 | 30 | 90>(14);
  const [filters, setFilters] = useState<AdminDashboardQueryParams>({});

  const handleSelectChange =
    (key: keyof AdminDashboardQueryParams) =>
    (event: React.ChangeEvent<HTMLSelectElement>) => {
      const value = event.target.value;
      setFilters((prev) => ({
        ...prev,
        [key]: value === "" ? null : value,
      }));
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

      <AgileKpiStrip data={null} loading={false} />

      <div
        className="grid grid-cols-1 gap-4 lg:grid-cols-2"
        data-testid="agile-dashboard-sections"
      >
        <AgileCfd data={null} loading={false} />
        {PLACEHOLDER_SECTIONS.map((section) => (
          <article
            key={section.id}
            data-testid={section.testId}
            className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-card/40 p-4 sm:p-5"
          >
            <h3 className="text-sm font-semibold text-foreground">
              {section.title}
            </h3>
            <p className="text-xs text-muted-foreground">{section.description}</p>
            <div className="mt-1 h-24 rounded-lg bg-muted/40" aria-hidden />
          </article>
        ))}
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
