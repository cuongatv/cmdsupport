"use client";

import React from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { archiveTaskProject } from "@/lib/task-api";
import { formatTaskDate } from "@/lib/task-types";
import type { TaskProject } from "@/lib/task-types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";

export type ScopeOption = { id: string; name: string };

type TaskProjectListProps = {
  projects: TaskProject[];
  loading: boolean;
  canManage: boolean;
  workspaces: ScopeOption[];
  departments: ScopeOption[];
  onEdit: (project: TaskProject) => void;
  onArchived: () => void;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export function TaskProjectList({
  projects,
  loading,
  canManage,
  workspaces,
  departments,
  onEdit,
  onArchived,
}: TaskProjectListProps) {
  const [error, setError] = React.useState("");
  const [archivingId, setArchivingId] = React.useState<string | null>(null);

  const workspaceMap = React.useMemo(
    () => Object.fromEntries(workspaces.map((w) => [w.id, w.name])),
    [workspaces]
  );
  const departmentMap = React.useMemo(
    () => Object.fromEntries(departments.map((d) => [d.id, d.name])),
    [departments]
  );

  const handleArchive = async (project: TaskProject) => {
    if (project.is_archived) return;
    if (
      !confirm(
        `Lưu trữ dự án "${project.name}"? Dự án sẽ được ẩn khỏi danh sách mặc định.`
      )
    )
      return;
    setError("");
    setArchivingId(project.id);
    try {
      await archiveTaskProject(project.id);
      onArchived();
    } catch (err) {
      setError(getErrorMessage(err, "Lưu trữ thất bại"));
    } finally {
      setArchivingId(null);
    }
  };

  if (loading) {
    return (
      <div className="bg-card rounded-xl border border-border shadow-sahara flex items-center justify-center py-16">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="bg-card rounded-xl border border-border shadow-sahara">
        <EmptyState
          icon="folder_managed"
          title="Chưa có dự án công việc nào"
          description="Tạo dự án đầu tiên để bắt đầu giao việc cho đội ngũ."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <div
          className="text-sm text-destructive bg-destructive/10 px-4 py-2 rounded-lg flex items-center gap-2"
          role="alert"
          data-testid="task-project-list-error"
        >
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </div>
      )}

      <div className="rounded-xl border border-border bg-card shadow-sahara overflow-hidden">
        <Table data-testid="task-project-table">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                Dự án
              </TableHead>
              <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                Phạm vi
              </TableHead>
              <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                Quyền giao
              </TableHead>
              <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                Trạng thái
              </TableHead>
              <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                Tạo lúc
              </TableHead>
              <TableHead className="w-[160px] text-right" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {projects.map((project) => {
              const isWorkspaceScope = !!project.workspace_id;
              const scopeName = isWorkspaceScope
                ? workspaceMap[project.workspace_id ?? ""] ??
                  "Không gian nghiệp vụ"
                : departmentMap[project.department_id ?? ""] ?? "Đơn vị";
              const scopeIcon = isWorkspaceScope ? "workspaces" : "domain";
              return (
                <TableRow
                  key={project.id}
                  data-testid={`task-project-row-${project.identifier}`}
                  className="group"
                >
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[11px] font-semibold text-muted-foreground">
                          {project.identifier}
                        </span>
                        <span className="font-medium text-foreground">
                          {project.name}
                        </span>
                      </div>
                      {project.description && (
                        <p className="text-xs text-muted-foreground line-clamp-2 max-w-md">
                          {project.description}
                        </p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1.5 text-sm text-foreground">
                      <span className="material-symbols-outlined text-base text-muted-foreground">
                        {scopeIcon}
                      </span>
                      {scopeName}
                    </span>
                  </TableCell>
                  <TableCell>
                    {project.allow_any_employee ? (
                      <Badge
                        variant="outline"
                        className="border-emerald-200 bg-emerald-50 text-emerald-700"
                      >
                        Tất cả nhân viên
                      </Badge>
                    ) : (
                      <Badge variant="outline">Theo phạm vi</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {project.is_archived ? (
                      <Badge
                        variant="outline"
                        className="border-muted bg-muted/30 text-muted-foreground"
                      >
                        Đã lưu trữ
                      </Badge>
                    ) : (
                      <Badge
                        variant="outline"
                        className="border-primary/20 bg-primary/5 text-primary"
                      >
                        Đang hoạt động
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-muted-foreground">
                      {formatTaskDate(project.created_at)}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Link
                        href={`/admin/tasks/projects/${project.id}`}
                        className={cn(
                          buttonVariants({ variant: "ghost", size: "sm" })
                        )}
                        data-testid={`task-project-dashboard-${project.identifier}`}
                      >
                        <span className="material-symbols-outlined text-sm">
                          dashboard
                        </span>
                        Xem bảng điều khiển
                      </Link>
                      {canManage && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onEdit(project)}
                            data-testid={`task-project-edit-${project.identifier}`}
                          >
                            Sửa
                          </Button>
                          {!project.is_archived && (
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={archivingId === project.id}
                              onClick={() => handleArchive(project)}
                              data-testid={`task-project-archive-${project.identifier}`}
                              className="text-muted-foreground hover:text-destructive"
                            >
                              {archivingId === project.id
                                ? "Đang lưu…"
                                : "Lưu trữ"}
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
