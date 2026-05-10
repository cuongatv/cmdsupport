"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { listTaskProjects } from "@/lib/task-api";
import type { TaskProject } from "@/lib/task-types";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import {
  TaskProjectDialog,
  type ScopeOption,
} from "@/components/tasks/task-project-dialog";
import { TaskProjectList } from "@/components/tasks/task-project-list";

type WorkspaceResponse = {
  id: string;
  name: string;
};

type DepartmentResponse = {
  id: string;
  name: string;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export default function TaskProjectsAdminPage() {
  const { hasPermission, user, loading: authLoading } = useAuth();

  const canRead =
    hasPermission("task:read:own_dept") || hasPermission("task:read:all");
  const canManage =
    hasPermission("task_project:manage:own_dept") ||
    hasPermission("task_project:manage:all");

  const [projects, setProjects] = useState<TaskProject[]>([]);
  const [workspaces, setWorkspaces] = useState<ScopeOption[]>([]);
  const [departments, setDepartments] = useState<ScopeOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editProject, setEditProject] = useState<TaskProject | null>(null);

  const loadProjects = useCallback(async () => {
    if (!canRead) {
      setProjects([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setPageError("");
    try {
      const data = await listTaskProjects({ include_archived: includeArchived });
      setProjects(data);
    } catch (err) {
      setProjects([]);
      setPageError(getErrorMessage(err, "Không tải được danh sách dự án"));
    } finally {
      setLoading(false);
    }
  }, [canRead, includeArchived]);

  const loadScopes = useCallback(async () => {
    if (!canRead) return;
    try {
      const [workspacesData, departmentsData] = await Promise.all([
        api<WorkspaceResponse[]>("/api/projects").catch(() => []),
        api<DepartmentResponse[]>("/api/departments").catch(() => []),
      ]);
      setWorkspaces(
        workspacesData.map((w) => ({ id: w.id, name: w.name }))
      );
      setDepartments(
        departmentsData.map((d) => ({ id: d.id, name: d.name }))
      );
    } catch {
      setWorkspaces([]);
      setDepartments([]);
    }
  }, [canRead]);

  // Defer the load to the next tick so React doesn't see a setState issued
  // synchronously from inside the effect body (react-hooks/set-state-in-effect).
  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadProjects();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadProjects]);

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadScopes();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadScopes]);

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

  // Fall back to the user's own department when the departments endpoint is
  // not accessible (e.g. department-scoped managers without org:departments:read).
  // React Compiler memoizes this expression automatically — no useMemo needed.
  const fallbackDepartment: ScopeOption | null =
    user && user.department_id && user.department_name
      ? { id: user.department_id, name: user.department_name }
      : null;
  const dialogDepartments: ScopeOption[] =
    departments.length > 0
      ? departments
      : fallbackDepartment
        ? [fallbackDepartment]
        : [];

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

  return (
    <>
      <PageHeader
        title="Dự án công việc"
        description="Quản lý các dự án công việc theo không gian nghiệp vụ hoặc đơn vị. Mỗi dự án có trạng thái, nhãn và quyền giao việc riêng."
        action={
          canManage ? (
            <Button
              data-testid="task-project-create-btn"
              onClick={handleCreate}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <span className="material-symbols-outlined text-base mr-1">
                add
              </span>
              Tạo dự án công việc
            </Button>
          ) : undefined
        }
      />

      <div className="flex flex-col gap-4 mt-6">
        <div className="flex items-center justify-end gap-3">
          <label className="inline-flex items-center gap-2 text-sm text-muted-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
              className="h-4 w-4 rounded border-input"
              data-testid="task-project-include-archived"
            />
            Hiển thị dự án đã lưu trữ
          </label>
        </div>

        {pageError && (
          <div
            className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center gap-2"
            role="alert"
            data-testid="task-project-page-error"
          >
            <span className="material-symbols-outlined text-base">error</span>
            {pageError}
          </div>
        )}

        <TaskProjectList
          projects={projects}
          loading={loading}
          canManage={canManage}
          workspaces={workspaces}
          departments={departments}
          onEdit={handleEdit}
          onArchived={handleSaved}
        />
      </div>

      {canManage && dialogOpen && (
        <TaskProjectDialog
          key={editProject?.id ?? "new-task-project"}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          project={editProject}
          workspaces={workspaces}
          departments={dialogDepartments}
          onSaved={handleSaved}
        />
      )}
    </>
  );
}
