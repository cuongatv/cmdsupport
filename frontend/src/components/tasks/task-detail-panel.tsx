"use client";

import React from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { deleteTask, listTasks } from "@/lib/task-api";
import { TaskForwardDialog } from "@/components/tasks/task-forward-dialog";
import {
  formatTaskDate,
  formatTaskDateTime,
} from "@/lib/task-types";
import type {
  EligibleAssignee,
  Task,
  TaskLabel,
  TaskPriority,
  TaskProject,
  TaskState,
} from "@/lib/task-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { TaskActivityFeed } from "@/components/tasks/task-activity";
import { TaskAttachments } from "@/components/tasks/task-attachments";
import { TaskComments } from "@/components/tasks/task-comments";
import { TaskDialog } from "@/components/tasks/task-dialog";
import { translateStateName } from "@/lib/task-i18n";

const PRIORITY_LABELS: Record<TaskPriority, string> = {
  none: "Không có",
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  urgent: "Khẩn cấp",
};

const PRIORITY_CLASSES: Record<TaskPriority, string> = {
  none: "border-border text-muted-foreground bg-background",
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  high: "bg-orange-50 text-orange-700 border-orange-200",
  urgent: "bg-red-50 text-red-700 border-red-200",
};

export type TaskDetailPanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task: Task;
  project: TaskProject;
  states: TaskState[];
  labels: TaskLabel[];
  eligibleAssignees: EligibleAssignee[];
  parentCandidates: Task[];
  canEdit: boolean;
  canDelete: boolean;
  onChanged: () => void;
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function MetaItem({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
        {label}
      </span>
      <div>{children}</div>
    </div>
  );
}

export function TaskDetailPanel({
  open,
  onOpenChange,
  task,
  project,
  states,
  labels,
  eligibleAssignees,
  parentCandidates,
  canEdit,
  canDelete,
  onChanged,
}: TaskDetailPanelProps) {
  const { user } = useAuth();
  const currentUserId = user?.id ?? null;

  const [editOpen, setEditOpen] = React.useState(false);
  const [forwardOpen, setForwardOpen] = React.useState(false);
  const [createSubtaskOpen, setCreateSubtaskOpen] = React.useState(false);
  const [subtasks, setSubtasks] = React.useState<Task[]>([]);
  const [subtasksLoading, setSubtasksLoading] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [error, setError] = React.useState("");

  const canForward =
    canEdit && task.completed_at === null && task.deleted_at === null;

  const isSubtask = task.parent_task_id !== null;
  const state = states.find((s) => s.id === task.state_id) ?? null;
  const parentTask = isSubtask
    ? parentCandidates.find((p) => p.id === task.parent_task_id) ?? null
    : null;

  const loadSubtasks = React.useCallback(async () => {
    if (isSubtask) {
      // Sub-subtasks not allowed → never any children to fetch.
      setSubtasks([]);
      return;
    }
    setSubtasksLoading(true);
    try {
      const res = await listTasks({
        task_project_id: project.id,
        page: 1,
        page_size: 100,
      });
      const children = res.items.filter(
        (t) => t.parent_task_id === task.id
      );
      setSubtasks(children);
    } catch {
      setSubtasks([]);
    } finally {
      setSubtasksLoading(false);
    }
  }, [isSubtask, project.id, task.id]);

  React.useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadSubtasks();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadSubtasks]);

  const handleDelete = async () => {
    if (
      !confirm(
        `Xóa công việc "${task.title}"? Hành động này không thể hoàn tác.`
      )
    ) {
      return;
    }
    setError("");
    setDeleting(true);
    try {
      await deleteTask(task.id);
      onChanged();
      onOpenChange(false);
    } catch (err) {
      setError(getErrorMessage(err, "Xóa công việc thất bại"));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl flex items-start gap-2">
              <span className="rounded-md bg-secondary px-1.5 py-0.5 text-[11px] font-semibold text-muted-foreground mt-1">
                {project.identifier}
              </span>
              <span className="flex-1" data-testid="task-detail-title">
                {task.title}
              </span>
            </DialogTitle>
          </DialogHeader>

          <div className="flex flex-col gap-4 mt-2">
            {error && (
              <p
                className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
                data-testid="task-detail-error"
                role="alert"
              >
                {error}
              </p>
            )}

            <div
              className="grid grid-cols-1 sm:grid-cols-3 gap-3"
              data-testid="task-detail-meta"
            >
              <MetaItem label="Trạng thái">
                {state ? (
                  <Badge
                    variant="outline"
                    className="border-primary/20 bg-primary/5 text-primary"
                  >
                    {translateStateName(state.name)}
                  </Badge>
                ) : (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </MetaItem>
              <MetaItem label="Ưu tiên">
                <Badge
                  variant="outline"
                  className={PRIORITY_CLASSES[task.priority] ?? ""}
                >
                  {PRIORITY_LABELS[task.priority] ?? task.priority}
                </Badge>
              </MetaItem>
              <MetaItem label="Ngày hết hạn">
                <span className="text-sm tabular-nums">
                  {formatTaskDate(task.due_date)}
                </span>
              </MetaItem>
              <MetaItem label="Phiên bản">
                <span className="text-sm tabular-nums">v{task.version}</span>
              </MetaItem>
              <MetaItem label="Tạo lúc">
                <span className="text-sm">
                  {formatTaskDateTime(task.created_at)}
                </span>
              </MetaItem>
              <MetaItem label="Cập nhật">
                <span className="text-sm">
                  {formatTaskDateTime(task.updated_at)}
                </span>
              </MetaItem>
            </div>

            {isSubtask && (
              <div
                className="rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground flex items-center gap-1.5"
                data-testid="task-detail-parent"
              >
                <span className="material-symbols-outlined text-sm">
                  subdirectory_arrow_right
                </span>
                Nhiệm vụ con của:{" "}
                <span className="font-medium text-foreground">
                  {parentTask?.title ?? "—"}
                </span>
              </div>
            )}

            {task.description && (
              <div className="flex flex-col gap-1.5">
                <span className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Mô tả
                </span>
                <p className="text-sm text-foreground whitespace-pre-wrap">
                  {task.description}
                </p>
              </div>
            )}

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                  Nhiệm vụ con
                </span>
                {!isSubtask && canEdit && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCreateSubtaskOpen(true)}
                    data-testid="task-detail-add-subtask"
                  >
                    <span className="material-symbols-outlined text-sm">
                      add
                    </span>
                    Thêm nhiệm vụ con
                  </Button>
                )}
              </div>
              {isSubtask ? (
                <p
                  className="text-xs text-muted-foreground"
                  data-testid="task-detail-no-subsubtask"
                >
                  Không thể thêm nhiệm vụ con cho một nhiệm vụ con.
                </p>
              ) : subtasksLoading ? (
                <span className="material-symbols-outlined text-sm text-muted-foreground animate-spin">
                  progress_activity
                </span>
              ) : subtasks.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Chưa có nhiệm vụ con nào.
                </p>
              ) : (
                <ul
                  className="flex flex-col gap-1"
                  data-testid="task-detail-subtask-list"
                >
                  {subtasks.map((sub) => (
                    <li
                      key={sub.id}
                      className="flex items-center gap-2 rounded-md border border-border bg-background px-2.5 py-1.5"
                      data-testid={`task-detail-subtask-${sub.id}`}
                    >
                      <span className="material-symbols-outlined text-sm text-muted-foreground">
                        subdirectory_arrow_right
                      </span>
                      <span className="flex-1 truncate text-sm">
                        {sub.title}
                      </span>
                      <Badge
                        variant="outline"
                        className={PRIORITY_CLASSES[sub.priority] ?? ""}
                      >
                        {PRIORITY_LABELS[sub.priority] ?? sub.priority}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="pt-3 border-t border-border">
              <Tabs defaultValue="comments" className="gap-3">
                <TabsList
                  className="w-full justify-start"
                  data-testid="task-detail-tabs"
                >
                  <TabsTrigger
                    value="comments"
                    data-testid="task-detail-tab-comments"
                  >
                    <span className="material-symbols-outlined text-sm">
                      forum
                    </span>
                    Bình luận
                  </TabsTrigger>
                  <TabsTrigger
                    value="attachments"
                    data-testid="task-detail-tab-attachments"
                  >
                    <span className="material-symbols-outlined text-sm">
                      attachment
                    </span>
                    Tệp đính kèm
                  </TabsTrigger>
                  <TabsTrigger
                    value="activity"
                    data-testid="task-detail-tab-activity"
                  >
                    <span className="material-symbols-outlined text-sm">
                      history
                    </span>
                    Hoạt động
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="comments" className="mt-1">
                  <TaskComments
                    taskId={task.id}
                    currentUserId={currentUserId}
                    eligibleAssignees={eligibleAssignees}
                  />
                </TabsContent>
                <TabsContent value="attachments" className="mt-1">
                  <TaskAttachments taskId={task.id} canDelete={canEdit} />
                </TabsContent>
                <TabsContent value="activity" className="mt-1">
                  <TaskActivityFeed
                    taskId={task.id}
                    eligibleAssignees={eligibleAssignees}
                    states={states}
                  />
                </TabsContent>
              </Tabs>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 mt-2 pt-3 border-t border-border">
              {canDelete ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleDelete}
                  disabled={deleting}
                  data-testid="task-detail-delete-btn"
                  className="text-destructive hover:bg-destructive/10"
                >
                  <span className="material-symbols-outlined text-sm">
                    delete
                  </span>
                  {deleting ? "Đang xóa…" : "Xóa công việc"}
                </Button>
              ) : (
                <span />
              )}
              <div className="flex gap-2 ml-auto">
                <Button
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                >
                  Đóng
                </Button>
                {canForward && (
                  <Button
                    variant="outline"
                    onClick={() => setForwardOpen(true)}
                    data-testid="task-detail-forward-btn"
                  >
                    <span className="material-symbols-outlined text-sm">
                      forward
                    </span>
                    Chuyển tiếp
                  </Button>
                )}
                {canEdit && (
                  <Button
                    onClick={() => setEditOpen(true)}
                    data-testid="task-detail-edit-btn"
                    className="bg-primary text-primary-foreground hover:bg-primary/90"
                  >
                    <span className="material-symbols-outlined text-sm">
                      edit
                    </span>
                    Chỉnh sửa
                  </Button>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {editOpen && (
        <TaskDialog
          key={`edit-${task.id}-${task.version}`}
          open={editOpen}
          onOpenChange={setEditOpen}
          task={task}
          project={project}
          states={states}
          labels={labels}
          eligibleAssignees={eligibleAssignees}
          parentCandidates={parentCandidates}
          onSaved={() => {
            onChanged();
            setEditOpen(false);
            onOpenChange(false);
          }}
        />
      )}

      {createSubtaskOpen && (
        <TaskDialog
          key={`subtask-${task.id}`}
          open={createSubtaskOpen}
          onOpenChange={setCreateSubtaskOpen}
          task={null}
          project={project}
          states={states}
          labels={labels}
          eligibleAssignees={eligibleAssignees}
          parentCandidates={parentCandidates}
          defaultParentTaskId={task.id}
          onSaved={() => {
            onChanged();
            setCreateSubtaskOpen(false);
            void loadSubtasks();
          }}
        />
      )}

      {forwardOpen && (
        <TaskForwardDialog
          key={`forward-${task.id}-${task.version}`}
          open={forwardOpen}
          onOpenChange={setForwardOpen}
          task={task}
          sourceDepartmentId={project.department_id}
          currentAssigneeIds={[]}
          currentUserId={currentUserId}
          onForwarded={() => {
            onChanged();
            setForwardOpen(false);
            onOpenChange(false);
          }}
        />
      )}
    </>
  );
}
