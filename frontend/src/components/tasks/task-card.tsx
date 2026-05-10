"use client";

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { Task, TaskPriority } from "@/lib/task-types";
import { formatTaskDate } from "@/lib/task-types";
import { Badge } from "@/components/ui/badge";

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

function priorityLabel(priority: string): string {
  return PRIORITY_LABELS[priority as TaskPriority] ?? priority;
}

function priorityClass(priority: string): string {
  return PRIORITY_CLASSES[priority as TaskPriority] ?? PRIORITY_CLASSES.none;
}

function stripHtml(value: string): string {
  return value.replace(/<[^>]*>/g, "").trim();
}

export type TaskCardProps = {
  task: Task;
  onClick?: (task: Task) => void;
  isOverlay?: boolean;
};

export function TaskCard({ task, onClick, isOverlay = false }: TaskCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: task.id,
    data: { task, type: "task" },
    disabled: isOverlay,
  });

  const style = isOverlay
    ? undefined
    : {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.4 : 1,
      };

  const description = task.description ? stripHtml(task.description) : "";

  return (
    <div
      ref={isOverlay ? undefined : setNodeRef}
      style={style}
      data-testid={`task-card-${task.title}`}
      className={`group rounded-lg border border-border bg-card p-3 shadow-sm transition-shadow hover:border-primary/40 hover:shadow-md ${
        isOverlay ? "rotate-2 cursor-grabbing shadow-lg" : "cursor-grab active:cursor-grabbing"
      }`}
      {...(isOverlay ? {} : attributes)}
      {...(isOverlay ? {} : listeners)}
      onClick={(event) => {
        if (isOverlay) return;
        // Suppress click after drag movement (dnd-kit fires synthetic click)
        if (isDragging) return;
        event.stopPropagation();
        onClick?.(task);
      }}
    >
      <div className="flex flex-col gap-2">
        <div className="text-sm font-medium leading-snug text-foreground line-clamp-2">
          {task.title}
        </div>
        {description && (
          <p className="line-clamp-2 text-xs text-muted-foreground">
            {description}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Badge
            variant="outline"
            className={`text-[10px] px-1.5 py-0 ${priorityClass(task.priority)}`}
          >
            {priorityLabel(task.priority)}
          </Badge>
          {task.due_date && (
            <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground tabular-nums">
              <span className="material-symbols-outlined text-[12px]">
                event
              </span>
              {formatTaskDate(task.due_date)}
            </span>
          )}
          {task.parent_task_id && (
            <span
              className="inline-flex items-center gap-1 text-[10px] text-muted-foreground"
              title="Nhiệm vụ con"
            >
              <span className="material-symbols-outlined text-[12px]">
                subdirectory_arrow_right
              </span>
              con
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
