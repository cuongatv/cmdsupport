"use client";

import * as React from "react";
import { ApiError } from "@/lib/api";
import { FEATURE_AGILE_PHASE_3 } from "@/lib/feature-flags";
import { getSquadCapacity } from "@/lib/task-api";
import type { SquadMemberCapacity } from "@/lib/task-types";

// Phase 3 (FEATURE_AGILE_PHASE_3) — Squad capacity overview panel. Read-only
// projection of `GET /api/departments/{department_id}/agile/capacity`. Hidden
// entirely when the flag is OFF so legacy deployments stay untouched. Strings
// are hardcoded Vietnamese per the project decision to avoid pulling in an
// i18n framework.
//
// Column headers and the overload status cell use stable Vietnamese copy
// alongside `data-testid` attributes so Wave 2 QA can drive the panel without
// depending on the visible text.

type SquadCapacityPanelProps = {
  departmentId: string;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

function isFlagOn(): boolean {
  return FEATURE_AGILE_PHASE_3;
}

// "—" is the canonical placeholder used elsewhere in the task UI (see
// `formatTaskDate` in `task-types.ts`). Keep parity for visual consistency
// when `story_points_sum` is null (no estimated tasks).
function formatStoryPoints(value: number | null): string {
  if (value === null) return "—";
  return String(value);
}

function formatCapacityPercent(value: number): string {
  // The backend stores capacity as an integer percent (e.g. 100 = full-time).
  // Render with the unit so the column header (% sign) and cell line up.
  return `${value}%`;
}

export function SquadCapacityPanel({ departmentId }: SquadCapacityPanelProps) {
  const [rows, setRows] = React.useState<SquadMemberCapacity[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string>("");

  const refresh = React.useCallback(async () => {
    if (!isFlagOn()) return;
    setLoading(true);
    setError("");
    try {
      const items = await getSquadCapacity(departmentId);
      setRows(items);
    } catch (err) {
      setError(getErrorMessage(err, "Không tải được dữ liệu năng lực"));
    } finally {
      setLoading(false);
    }
  }, [departmentId]);

  React.useEffect(() => {
    // Defer to a microtask to dodge the `react-hooks/set-state-in-effect`
    // rule the project downgrades to `warn` (see `eslint.config.mjs`).
    const timerId = window.setTimeout(() => {
      refresh();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [refresh]);

  if (!isFlagOn()) {
    // Phase 3 OFF — render nothing. Caller can still mount this component
    // unconditionally; the flag check lives here so the gate is co-located
    // with the feature.
    return null;
  }

  return (
    <section
      className="flex flex-col gap-3 rounded-xl border border-border bg-card/40 p-4"
      data-testid="squad-capacity-panel"
    >
      <header className="flex flex-col gap-0.5">
        <h2 className="text-base font-semibold tracking-tight text-foreground">
          Năng lực đội nhóm
        </h2>
        <p className="text-xs text-muted-foreground">
          Tổng quan tải công việc theo từng thành viên trong các squad của
          phòng ban.
        </p>
      </header>

      {error && (
        <div
          className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
          data-testid="squad-capacity-panel-error"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div
          className="text-sm text-muted-foreground"
          data-testid="squad-capacity-panel-loading"
        >
          Đang tải dữ liệu năng lực…
        </div>
      ) : rows.length === 0 ? (
        <div
          className="rounded-lg border border-dashed border-border bg-secondary/30 px-4 py-6 text-center text-sm text-muted-foreground"
          data-testid="squad-capacity-panel-empty"
        >
          Chưa có dữ liệu năng lực
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <th scope="col" className="px-3 py-2 font-medium">
                  Thành viên
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Năng lực (%)
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Công việc mở
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Điểm ước lượng
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Trạng thái
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <CapacityRow key={`${row.employee_id}-${row.squad_name}`} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

type CapacityRowProps = {
  row: SquadMemberCapacity;
};

function CapacityRow({ row }: CapacityRowProps) {
  return (
    <tr
      className="border-b border-border/60 last:border-b-0 hover:bg-secondary/40"
      data-testid={`capacity-row-${row.employee_id}`}
    >
      <td className="px-3 py-2">
        <div className="flex flex-col">
          <span className="font-medium text-foreground">{row.employee_name}</span>
          <span className="text-xs text-muted-foreground">{row.squad_name}</span>
        </div>
      </td>
      <td className="px-3 py-2 text-foreground">
        {formatCapacityPercent(row.capacity_percent)}
      </td>
      <td className="px-3 py-2 text-foreground">{row.open_task_count}</td>
      <td className="px-3 py-2 text-foreground">
        {formatStoryPoints(row.story_points_sum)}
      </td>
      <td className="px-3 py-2">
        {row.is_overloaded ? (
          <span
            className="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-semibold text-destructive"
            data-testid={`capacity-status-${row.employee_id}`}
          >
            Quá tải
          </span>
        ) : (
          <span
            className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-100"
            data-testid={`capacity-status-${row.employee_id}`}
          >
            Bình thường
          </span>
        )}
      </td>
    </tr>
  );
}
