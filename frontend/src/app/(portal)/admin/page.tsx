"use client";

import { useCallback, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ClassicDashboardView } from "@/components/admin/dashboard/ClassicDashboardView";
import { AgileDashboardShell } from "@/components/admin/dashboard/AgileDashboardShell";

// Re-export the legacy `Project` type so any external callers that imported
// it from this route file keep compiling. The canonical definition now
// lives next to the view that owns the fetch.
export type { Project } from "@/components/admin/dashboard/ClassicDashboardView";

type DashboardView = "classic" | "agile";

const VIEW_OPTIONS: { value: DashboardView; label: string; testId: string }[] = [
  {
    value: "classic",
    label: "Theo dõi công việc thông thường",
    testId: "dashboard-view-classic",
  },
  {
    value: "agile",
    label: "Theo dõi công việc Agile",
    testId: "dashboard-view-agile",
  },
];

function parseView(value: string | null): DashboardView {
  return value === "agile" ? "agile" : "classic";
}

export default function DashboardPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const view = useMemo(
    () => parseView(searchParams.get("view")),
    [searchParams],
  );

  const setView = useCallback(
    (next: DashboardView) => {
      if (next === view) return;
      const params = new URLSearchParams(searchParams.toString());
      if (next === "classic") {
        // `classic` is the default — keep the URL clean.
        params.delete("view");
      } else {
        params.set("view", next);
      }
      const query = params.toString();
      router.replace(query ? `/admin?${query}` : "/admin", { scroll: false });
    },
    [router, searchParams, view],
  );

  return (
    <div className="flex flex-col gap-4">
      <div
        data-testid="dashboard-view-toggle"
        role="tablist"
        aria-label="Chế độ theo dõi công việc"
        className="inline-flex w-fit items-center gap-1 rounded-full border border-border bg-card p-1 shadow-sm"
      >
        {VIEW_OPTIONS.map((option) => {
          const isActive = option.value === view;
          return (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              data-testid={option.testId}
              data-active={isActive ? "true" : "false"}
              onClick={() => setView(option.value)}
              className={
                "rounded-full px-4 py-1.5 text-sm font-medium transition-colors " +
                (isActive
                  ? "bg-primary text-primary-foreground shadow"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground")
              }
            >
              {option.label}
            </button>
          );
        })}
      </div>

      {view === "classic" ? <ClassicDashboardView /> : <AgileDashboardShell />}
    </div>
  );
}
