"use client";

import React from "react";
import type {
  EligibleAssignee,
  Task,
  TaskPriority,
  TaskProject,
  TaskState,
} from "@/lib/task-types";
import { formatTaskDate } from "@/lib/task-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";
import { TASK_PRIORITY_LABELS } from "@/components/tasks/task-list-filters";
import { translateStateName } from "@/lib/task-i18n";

const PRIORITY_CLASSES: Record<TaskPriority, string> = {
  none: "border-border text-muted-foreground bg-background",
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  high: "bg-orange-50 text-orange-700 border-orange-200",
  urgent: "bg-red-50 text-red-700 border-red-200",
};

type TaskListTableProps = {
  tasks: Task[];
  loading: boolean;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  projectMap: Record<string, TaskProject>;
  stateMap: Record<string, TaskState>;
  selectedAssignee: EligibleAssignee | null;
  emptyTitle: string;
  emptyDescription: string;
  emptyIcon?: string;
  onRowClick?: (task: Task) => void;
};

function priorityLabel(priority: string): string {
  return TASK_PRIORITY_LABELS[priority as TaskPriority] ?? priority;
}

function priorityClass(priority: string): string {
  return PRIORITY_CLASSES[priority as TaskPriority] ?? PRIORITY_CLASSES.none;
}

function stripHtml(value: string): string {
  return value.replace(/<[^>]*>/g, "");
}

export function TaskListTable({
  tasks,
  loading,
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  projectMap,
  stateMap,
  selectedAssignee,
  emptyTitle,
  emptyDescription,
  emptyIcon = "checklist",
  onRowClick,
}: TaskListTableProps) {
  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endIndex = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground tabular-nums">
          {total > 0
            ? `Hiển thị ${startIndex}–${endIndex} trên ${total} công việc`
            : `${total} công việc`}
        </span>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
              progress_activity
            </span>
          </div>
        ) : tasks.length === 0 ? (
          <EmptyState
            icon={emptyIcon}
            title={emptyTitle}
            description={emptyDescription}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Công việc
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Dự án
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Trạng thái
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Người nhận
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Ưu tiên
                </TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Hạn
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tasks.map((task) => {
                const project = projectMap[task.task_project_id] ?? null;
                const state = stateMap[task.state_id] ?? null;
                return (
                  <TableRow
                    key={task.id}
                    className={`group hover:bg-secondary/30 transition-colors ${
                      onRowClick ? "cursor-pointer" : ""
                    }`}
                    data-testid={`task-row-${task.id}`}
                    onClick={onRowClick ? () => onRowClick(task) : undefined}
                  >
                    <TableCell className="max-w-[420px]">
                      <div className="flex flex-col gap-1">
                        <span className="truncate font-medium text-foreground">
                          {task.title}
                        </span>
                        {task.description && (
                          <p className="truncate text-xs text-muted-foreground">
                            {stripHtml(task.description)}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      {project ? (
                        <div className="flex items-center gap-2">
                          <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[11px] font-semibold text-muted-foreground">
                            {project.identifier}
                          </span>
                          <span className="truncate text-sm text-foreground">
                            {project.name}
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground/60">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {state ? (
                        <Badge
                          variant="outline"
                          className="border-primary/20 bg-primary/5 text-primary"
                          title={translateStateName(state.name)}
                        >
                          {translateStateName(state.name)}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground/60">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {selectedAssignee ? (
                        <div className="flex items-center gap-2">
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-bold text-primary">
                            {selectedAssignee.name.charAt(0).toUpperCase()}
                          </span>
                          <span className="truncate text-sm text-foreground">
                            {selectedAssignee.name}
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground/60">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={priorityClass(task.priority)}
                      >
                        {priorityLabel(task.priority)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-muted-foreground tabular-nums">
                        {formatTaskDate(task.due_date)}
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            Trang {page} / {totalPages}
          </span>
          <div className="flex items-center gap-1" data-testid="task-pagination">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              className="h-8 px-2.5"
              aria-label="Trang trước"
            >
              <span className="material-symbols-outlined text-sm">chevron_left</span>
            </Button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              let p: number;
              if (totalPages <= 7) {
                p = i + 1;
              } else if (page <= 4) {
                p = i + 1;
              } else if (page >= totalPages - 3) {
                p = totalPages - 6 + i;
              } else {
                p = page - 3 + i;
              }
              return (
                <Button
                  key={p}
                  variant={p === page ? "default" : "outline"}
                  size="sm"
                  onClick={() => onPageChange(p)}
                  className={`h-8 w-8 p-0 text-xs ${
                    p === page ? "bg-primary text-primary-foreground" : ""
                  }`}
                  aria-current={p === page ? "page" : undefined}
                >
                  {p}
                </Button>
              );
            })}
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              className="h-8 px-2.5"
              aria-label="Trang sau"
            >
              <span className="material-symbols-outlined text-sm">chevron_right</span>
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
