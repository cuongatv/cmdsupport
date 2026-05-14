"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  listTaskProjects,
  listTasks,
  resolveTaskProject,
} from "@/lib/task-api";
import type { TaskProject } from "@/lib/task-types";
import { UNIT_TYPE_LABEL, type UnitType } from "@/lib/department-types";
import { Button } from "@/components/ui/button";
import {
  TaskProjectDialog,
  type ScopeOption,
} from "@/components/tasks/task-project-dialog";
import { TaskProjectList } from "@/components/tasks/task-project-list";
import { EmptyState } from "@/components/shared/empty-state";

type Props = {
  departmentId: string;
  unitType: UnitType;
  departmentName?: string;
};

// Three buckets the user can slice the project list by. Stored locally — no
// URL params yet, because the hub URL is already carrying `tab=work` and we
// want the filter to reset cleanly each time the user navigates back.
type WorkFilter = "open" | "overdue" | "all";

const FILTER_OPTIONS: ReadonlyArray<{
  key: WorkFilter;
  label: string;
  icon: string;
}> = [
  { key: "open", label: "Đang mở", icon: "play_circle" },
  { key: "overdue", label: "Quá hạn", icon: "schedule" },
  { key: "all", label: "Tất cả", icon: "list" },
];

// Cap mirrors `listTasks` server-side limit (`Query(le=100)` in
// `app/routers/tasks.py`). One call gives us enough overdue tasks across all
// projects in the department to flag which projects are "Quá hạn" without an
// N+1 dashboard fetch.
const OVERDUE_FETCH_LIMIT = 100;

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export function WorkTab({ departmentId, unitType, departmentName }: Props) {
  const router = useRouter();
  const { hasPermission } = useAuth();

  const canManage =
    hasPermission("task_project:manage:own_dept") ||
    hasPermission("task_project:manage:all");

  const [filter, setFilter] = useState<WorkFilter>("open");
  const [projects, setProjects] = useState<TaskProject[]>([]);
  const [overdueProjectIds, setOverdueProjectIds] = useState<Set<string>>(
    () => new Set()
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editProject, setEditProject] = useState<TaskProject | null>(null);

  const [openingGeneral, setOpeningGeneral] = useState(false);
  const [generalError, setGeneralError] = useState("");

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      // "Tất cả" is the only bucket that shows archived projects; everything
      // else filters down from the active set. Backend already returns
      // department-scoped projects when `department_id` is set.
      const includeArchived = filter === "all";
      const data = await listTaskProjects({
        department_id: departmentId,
        include_archived: includeArchived,
      });
      setProjects(data);

      if (filter === "overdue") {
        // Single department-wide query for overdue tasks; we only need the
        // distinct `task_project_id`s to mark which projects have overdue
        // work. listTasks already honors membership-union access (T8).
        const overdue = await listTasks({
          department_id: departmentId,
          overdue: true,
          page: 1,
          page_size: OVERDUE_FETCH_LIMIT,
        });
        setOverdueProjectIds(
          new Set(overdue.items.map((t) => t.task_project_id))
        );
      } else {
        setOverdueProjectIds(new Set());
      }
    } catch (err) {
      setProjects([]);
      setOverdueProjectIds(new Set());
      setError(getErrorMessage(err, "Không tải được dự án công việc"));
    } finally {
      setLoading(false);
    }
  }, [departmentId, filter]);

  useEffect(() => {
    // Match the deferred-load pattern used elsewhere in the portal so the
    // React 19 compiler does not flag setState-in-effect inside loadProjects.
    const timerId = window.setTimeout(() => {
      void loadProjects();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadProjects]);

  const visibleProjects = useMemo(() => {
    if (filter === "overdue") {
      return projects.filter((p) => overdueProjectIds.has(p.id));
    }
    return projects;
  }, [projects, filter, overdueProjectIds]);

  const departmentsForDialog: ScopeOption[] = useMemo(
    () => [
      {
        id: departmentId,
        name: departmentName?.trim() || "Đơn vị này",
      },
    ],
    [departmentId, departmentName]
  );

  const handleCreate = () => {
    setEditProject(null);
    setDialogOpen(true);
  };

  const handleEdit = (project: TaskProject) => {
    setEditProject(project);
    setDialogOpen(true);
  };

  const handleSaved = () => {
    void loadProjects();
  };

  const handleOpenGeneral = async () => {
    setGeneralError("");
    setOpeningGeneral(true);
    try {
      // Lazy-resolves (or reuses) the default "Công việc chung" project for
      // this department. Backend authorizes membership before creating —
      // non-members get TaskProjectAccessDenied (T8).
      const resolved = await resolveTaskProject({ department_id: departmentId });
      router.push(`/admin/tasks/projects/${resolved.id}`);
    } catch (err) {
      setGeneralError(getErrorMessage(err, "Không mở được Công việc chung"));
      setOpeningGeneral(false);
    }
  };

  const filterCounts = useMemo(() => {
    return {
      open: projects.filter((p) => !p.is_archived).length,
      overdue: overdueProjectIds.size,
      all: projects.length,
    };
  }, [projects, overdueProjectIds]);

  return (
    <div
      className="flex flex-col gap-5"
      data-testid="dept-tab-panel-work"
      data-department-id={departmentId}
    >
      {/* "Công việc chung" entry — always at the top, regardless of the
          filter below. Clicking lazy-resolves the default project then
          routes to its dashboard. */}
      <button
        type="button"
        onClick={handleOpenGeneral}
        disabled={openingGeneral}
        data-testid="dept-work-general"
        className="flex items-center justify-between gap-4 rounded-xl border border-border bg-card px-5 py-4 text-left shadow-sahara transition-colors hover:bg-muted/40 disabled:opacity-60 disabled:cursor-wait"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <span className="material-symbols-outlined text-primary">
              inbox
            </span>
          </div>
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="font-medium text-foreground">Công việc chung</span>
            <span className="text-xs text-muted-foreground">
              Bảng việc mặc định cho {UNIT_TYPE_LABEL[unitType]} — mở nhanh
              không cần tạo dự án riêng.
            </span>
          </div>
        </div>
        <span className="material-symbols-outlined text-muted-foreground shrink-0">
          {openingGeneral ? "progress_activity" : "arrow_forward"}
        </span>
      </button>

      {generalError && (
        <div
          className="text-sm text-destructive bg-destructive/10 px-4 py-2 rounded-lg flex items-center gap-2"
          role="alert"
          data-testid="dept-work-general-error"
        >
          <span className="material-symbols-outlined text-base">error</span>
          {generalError}
        </div>
      )}

      {/* Filter strip + create CTA */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div
          role="tablist"
          aria-label="Trạng thái dự án"
          className="inline-flex items-center gap-1 rounded-lg border border-border bg-background p-1"
          data-testid="dept-work-filter"
        >
          {FILTER_OPTIONS.map((opt) => {
            const selected = filter === opt.key;
            const count = filterCounts[opt.key];
            return (
              <button
                key={opt.key}
                type="button"
                role="tab"
                aria-selected={selected}
                data-testid={`dept-work-filter-${opt.key}`}
                onClick={() => setFilter(opt.key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
                  selected
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`}
              >
                <span className="material-symbols-outlined text-base">
                  {opt.icon}
                </span>
                {opt.label}
                {!loading && (
                  <span
                    className={`ml-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      selected
                        ? "bg-primary-foreground/15 text-primary-foreground"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {canManage && (
          <Button
            data-testid="dept-work-create-btn"
            onClick={handleCreate}
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <span className="material-symbols-outlined text-base mr-1">
              add
            </span>
            Tạo dự án công việc
          </Button>
        )}
      </div>

      {error && (
        <div
          className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center gap-2"
          role="alert"
          data-testid="dept-work-error"
        >
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </div>
      )}

      {/* When the filter narrows the list down to zero, show a filter-aware
          empty state instead of TaskProjectList's generic "no projects".
          Mirrors the pattern used in admin/tasks. */}
      {!loading && projects.length > 0 && visibleProjects.length === 0 ? (
        <div className="bg-card rounded-xl border border-border shadow-sahara">
          <EmptyState
            icon="filter_alt_off"
            title={
              filter === "overdue"
                ? "Không có dự án nào đang quá hạn"
                : "Không có dự án phù hợp bộ lọc"
            }
            description="Thử chuyển sang 'Tất cả' để xem mọi dự án thuộc đơn vị."
          />
        </div>
      ) : (
        <TaskProjectList
          projects={visibleProjects}
          loading={loading}
          canManage={canManage}
          workspaces={[]}
          departments={departmentsForDialog}
          onEdit={handleEdit}
          onArchived={handleSaved}
        />
      )}

      {canManage && dialogOpen && (
        <TaskProjectDialog
          key={editProject?.id ?? `new-task-project-${departmentId}`}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          project={editProject}
          workspaces={[]}
          departments={departmentsForDialog}
          onSaved={handleSaved}
          initialScope={editProject ? undefined : "department"}
          initialDepartmentId={editProject ? undefined : departmentId}
        />
      )}
    </div>
  );
}
