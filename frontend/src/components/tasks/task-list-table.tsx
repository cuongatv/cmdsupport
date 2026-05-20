"use client";

import React, { useState } from "react";
import { ApiError } from "@/lib/api";
import { moveTask, updateTask } from "@/lib/task-api";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

const PRIORITY_VALUES: TaskPriority[] = [
  "none",
  "low",
  "medium",
  "high",
  "urgent",
];

const POSITION_GAP = 1000;

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
  /**
   * All states for the currently selected project. Used to populate the
   * inline state dropdown. When empty (multi-project / scope view), the
   * state cell falls back to a read-only badge because cross-project
   * `state_id` moves have no unambiguous target — same constraint as
   * `TaskKanban`'s `groupedView` mode.
   */
  projectStates?: TaskState[];
  selectedAssignee: EligibleAssignee | null;
  emptyTitle: string;
  emptyDescription: string;
  emptyIcon?: string;
  onRowClick?: (task: Task) => void;
  /**
   * Called after a successful inline mutation (state or priority change).
   * Parent can use this to refresh derived data (dashboard counts, etc.)
   * — the row itself is updated optimistically and patched with the
   * server response, so the parent does NOT need to refetch the list.
   */
  onTaskMutated?: (task: Task) => void;
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

function getMutationErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return "Xung đột phiên bản, vui lòng tải lại.";
    if (err.message) return err.message;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
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
  projectStates,
  selectedAssignee,
  emptyTitle,
  emptyDescription,
  emptyIcon = "checklist",
  onRowClick,
  onTaskMutated,
}: TaskListTableProps) {
  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endIndex = Math.min(page * pageSize, total);

  // Local optimistic overlay keyed by task id. When a mutation succeeds the
  // server response replaces the optimistic patch; on failure we delete the
  // entry so the row falls back to the parent-provided `tasks` snapshot.
  const [optimistic, setOptimistic] = useState<Record<string, Task>>({});
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  const displayTasks = tasks.map((t) => optimistic[t.id] ?? t);

  // Sort and dedupe per-project states for the inline dropdown. Memoised so
  // the dropdown doesn't rebuild the list on every render of every row.
  const sortedProjectStates = React.useMemo(() => {
    if (!projectStates) return [];
    return [...projectStates].sort((a, b) => a.position - b.position);
  }, [projectStates]);

  const applyTask = (task: Task) => {
    setOptimistic((prev) => ({ ...prev, [task.id]: task }));
    onTaskMutated?.(task);
  };

  const handleStateChange = async (task: Task, nextStateId: string) => {
    if (nextStateId === task.state_id) return;
    if (!sortedProjectStates.some((s) => s.id === nextStateId)) return;

    // Compute append-to-end position in the target column, mirroring the
    // Kanban's cross-column behavior so the moved task lands at the bottom.
    const tasksInTarget = displayTasks.filter(
      (t) => t.state_id === nextStateId && t.id !== task.id,
    );
    const lastPosition = tasksInTarget.reduce(
      (max, t) => (t.position > max ? t.position : max),
      0,
    );
    const newPosition = lastPosition + POSITION_GAP;

    // Optimistic update — patch state_id immediately, then reconcile with
    // the server-returned task (which includes the new `version`).
    setOptimistic((prev) => ({
      ...prev,
      [task.id]: { ...task, state_id: nextStateId, position: newPosition },
    }));
    setPendingId(task.id);
    setErrorMessage("");

    try {
      const result = await moveTask(task.id, {
        state_id: nextStateId,
        position: newPosition,
        version: task.version,
      });
      applyTask(result.task);
    } catch (err) {
      // Rollback by removing the optimistic entry.
      setOptimistic((prev) => {
        const next = { ...prev };
        delete next[task.id];
        return next;
      });
      setErrorMessage(
        getMutationErrorMessage(err, "Không cập nhật được trạng thái."),
      );
    } finally {
      setPendingId((current) => (current === task.id ? null : current));
    }
  };

  const handlePriorityChange = async (
    task: Task,
    nextPriority: TaskPriority,
  ) => {
    if (nextPriority === task.priority) return;

    setOptimistic((prev) => ({
      ...prev,
      [task.id]: { ...task, priority: nextPriority },
    }));
    setPendingId(task.id);
    setErrorMessage("");

    try {
      const updated = await updateTask(task.id, {
        priority: nextPriority,
        version: task.version,
      });
      applyTask(updated);
    } catch (err) {
      setOptimistic((prev) => {
        const next = { ...prev };
        delete next[task.id];
        return next;
      });
      setErrorMessage(
        getMutationErrorMessage(err, "Không cập nhật được mức ưu tiên."),
      );
    } finally {
      setPendingId((current) => (current === task.id ? null : current));
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground tabular-nums">
          {total > 0
            ? `Hiển thị ${startIndex}–${endIndex} trên ${total} công việc`
            : `${total} công việc`}
        </span>
      </div>

      {errorMessage && (
        <div
          className="flex items-center gap-2 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive"
          role="alert"
          data-testid="task-list-error"
        >
          <span className="material-symbols-outlined text-base">error</span>
          {errorMessage}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
              progress_activity
            </span>
          </div>
        ) : displayTasks.length === 0 ? (
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
              {displayTasks.map((task) => {
                const project = projectMap[task.task_project_id] ?? null;
                const state = stateMap[task.state_id] ?? null;
                const isPending = pendingId === task.id;
                // Inline state dropdown is only available when the parent
                // passed the per-project state list AND the task belongs to
                // that project — same constraint that disables Kanban DnD in
                // grouped (multi-project) mode.
                const inlineStateAvailable =
                  sortedProjectStates.length > 0 &&
                  sortedProjectStates.some((s) => s.id === task.state_id);
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
                    <TableCell
                      onClick={
                        inlineStateAvailable
                          ? (e) => e.stopPropagation()
                          : undefined
                      }
                    >
                      {inlineStateAvailable ? (
                        <Select
                          value={task.state_id}
                          onValueChange={(value) => {
                            if (typeof value === "string") {
                              handleStateChange(task, value);
                            }
                          }}
                          disabled={isPending}
                        >
                          <SelectTrigger
                            size="sm"
                            className="h-7 min-w-[140px] border-primary/20 bg-primary/5 text-primary"
                            data-testid={`task-row-state-${task.id}`}
                          >
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {sortedProjectStates.map((s) => (
                              <SelectItem key={s.id} value={s.id}>
                                {translateStateName(s.name)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : state ? (
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
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Select
                        value={task.priority}
                        onValueChange={(value) => {
                          if (typeof value === "string") {
                            handlePriorityChange(task, value as TaskPriority);
                          }
                        }}
                        disabled={isPending}
                      >
                        <SelectTrigger
                          size="sm"
                          className={`h-7 min-w-[120px] ${priorityClass(
                            task.priority,
                          )}`}
                          data-testid={`task-row-priority-${task.id}`}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {PRIORITY_VALUES.map((p) => (
                            <SelectItem key={p} value={p}>
                              {priorityLabel(p)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
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
