"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  getTaskDashboard,
  getTaskProject,
  listSprints,
} from "@/lib/task-api";
import type { Sprint, TaskDashboard, TaskProject } from "@/lib/task-types";
import { FEATURE_AGILE_PHASE_5 } from "@/lib/feature-flags";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/page-header";
import { buttonVariants } from "@/components/ui/button";
import { TaskDashboardWidgets } from "@/components/tasks/task-dashboard";
import { FlowMetricsPanel } from "@/components/tasks/flow-metrics-panel";

type PageProps = {
  params: Promise<{ id: string }>;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export default function TaskProjectDashboardPage({ params }: PageProps) {
  // Next.js 16: `params` is a Promise. In a Client Component the canonical
  // unwrap is `React.use(params)` (cf. node_modules/next/dist/docs/01-app/02-guides/upgrading/version-16.md).
  const { id: projectId } = use(params);
  const { hasPermission, loading: authLoading } = useAuth();

  const canRead =
    hasPermission("task:read:own_dept") || hasPermission("task:read:all");

  const [project, setProject] = useState<TaskProject | null>(null);
  const [dashboard, setDashboard] = useState<TaskDashboard | null>(null);
  const [activeSprint, setActiveSprint] = useState<Sprint | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");

  const loadDashboard = useCallback(async () => {
    if (!canRead) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setPageError("");
    try {
      const [projectData, dashboardData] = await Promise.all([
        getTaskProject(projectId),
        getTaskDashboard(projectId),
      ]);
      setProject(projectData);
      setDashboard(dashboardData);
      // Phase 5: fetch active sprint so the FlowMetricsPanel can surface
      // the optional sprint commitment / completion cards. Failures are
      // non-fatal — the panel hides the sprint section when null.
      if (FEATURE_AGILE_PHASE_5) {
        try {
          const sprints = await listSprints(projectId);
          const active = sprints.find((s) => s.status === "active") ?? null;
          setActiveSprint(active);
        } catch {
          setActiveSprint(null);
        }
      } else {
        setActiveSprint(null);
      }
    } catch (err) {
      setProject(null);
      setDashboard(null);
      setActiveSprint(null);
      setPageError(
        getErrorMessage(err, "Không tải được bảng điều khiển dự án")
      );
    } finally {
      setLoading(false);
    }
  }, [canRead, projectId]);

  // Defer to next tick so React doesn't see a setState issued synchronously
  // from inside the effect body (react-hooks/set-state-in-effect).
  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadDashboard();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadDashboard]);

  if (authLoading) {
    return (
      <div className="text-sm text-muted-foreground">Đang xác thực…</div>
    );
  }

  if (!canRead) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
        Bạn không có quyền truy cập dự án công việc.
      </div>
    );
  }

  const description = project?.description?.trim()
    ? project.description
    : "Tổng quan công việc, phân bổ theo trạng thái và người thực hiện, cùng các công việc đến hạn trong tuần này.";
  const titleSuffix = project ? ` · ${project.identifier}` : "";

  return (
    <>
      <PageHeader
        title={`Bảng điều khiển${titleSuffix}`}
        description={description}
        action={
          <Link
            href="/admin/tasks/projects"
            className={cn(buttonVariants({ variant: "outline" }))}
            data-testid="task-dashboard-back-btn"
          >
            <span className="material-symbols-outlined text-sm">
              arrow_back
            </span>
            Quay lại danh sách
          </Link>
        }
      />

      <div className="mt-6 flex flex-col gap-5">
        {project && (
          <div
            className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground"
            data-testid="task-dashboard-project-meta"
          >
            <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[11px] font-semibold text-muted-foreground">
              {project.identifier}
            </span>
            <span className="font-medium text-foreground">{project.name}</span>
            {project.is_archived && (
              <span className="rounded-md border border-muted bg-muted/30 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                Đã lưu trữ
              </span>
            )}
          </div>
        )}

        {pageError && (
          <div
            className="flex items-center gap-2 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive"
            role="alert"
            data-testid="task-dashboard-error"
          >
            <span className="material-symbols-outlined text-base">error</span>
            {pageError}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center rounded-xl border border-border bg-card py-16 text-sm text-muted-foreground shadow-sahara">
            <span className="material-symbols-outlined mr-2 animate-spin text-base">
              progress_activity
            </span>
            Đang tải bảng điều khiển…
          </div>
        ) : dashboard ? (
          <>
            <TaskDashboardWidgets dashboard={dashboard} />
            {/* Phase 5 (FEATURE_AGILE_PHASE_5) — flow metrics overview.
                The panel renders nothing when the flag is OFF, so the
                conditional mount is harmless in legacy deployments. */}
            <FlowMetricsPanel
              projectId={projectId}
              activeSprint={activeSprint}
            />
          </>
        ) : !pageError ? (
          <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
            Không có dữ liệu để hiển thị.
          </div>
        ) : null}
      </div>
    </>
  );
}
