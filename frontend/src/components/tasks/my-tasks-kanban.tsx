"use client";

import { useEffect, useMemo, useState } from "react";
import {
  type CollisionDetection,
  DndContext,
  type DragEndEvent,
  type DragStartEvent,
  DragOverlay,
  PointerSensor,
  pointerWithin,
  rectIntersection,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ApiError } from "@/lib/api";
import { moveTask } from "@/lib/task-api";
import { translateStateName } from "@/lib/task-i18n";
import type { Task, TaskPriority, TaskState } from "@/lib/task-types";
import { formatTaskDate } from "@/lib/task-types";
import { Badge } from "@/components/ui/badge";

// The six canonical state groups the backend uses (see
// `app/services/task_constants.py` → DEFAULT_STATE_GROUPS). One column per
// group so "Công việc của tôi" — which spans many projects with different
// state vocabularies — collapses into a stable, predictable board. The
// keys MUST match `TaskState.group` exactly; mismatched keys make the
// column appear empty and silently break drag-to-different-group.
type StateGroup =
  | "backlog"
  | "todo"
  | "in_progress"
  | "review"
  | "done"
  | "cancelled";

const GROUP_ORDER: readonly StateGroup[] = [
  "backlog",
  "todo",
  "in_progress",
  "review",
  "done",
  "cancelled",
];

// Column labels match the unit Kanban exactly: pull each group's canonical
// backend state name (see app/services/task_constants.py → DEFAULT_STATE_NAMES)
// through the same `translateStateName` map admin Kanban uses
// (lib/task-i18n.ts). Keeping this indirection means future i18n tweaks
// affect both surfaces in lockstep — no drift between /admin/tasks and
// /me/tasks columns.
const GROUP_CANONICAL_STATE_NAME: Record<StateGroup, string> = {
  backlog: "Backlog",
  todo: "Todo",
  in_progress: "In Progress",
  review: "In Review",
  done: "Done",
  cancelled: "Cancelled",
};

const GROUP_LABELS: Record<StateGroup, string> = {
  backlog: translateStateName(GROUP_CANONICAL_STATE_NAME.backlog),
  todo: translateStateName(GROUP_CANONICAL_STATE_NAME.todo),
  in_progress: translateStateName(GROUP_CANONICAL_STATE_NAME.in_progress),
  review: translateStateName(GROUP_CANONICAL_STATE_NAME.review),
  done: translateStateName(GROUP_CANONICAL_STATE_NAME.done),
  cancelled: translateStateName(GROUP_CANONICAL_STATE_NAME.cancelled),
};

const GROUP_DOT_CLASSES: Record<StateGroup, string> = {
  backlog: "bg-muted-foreground/60",
  todo: "bg-sky-500",
  in_progress: "bg-amber-500",
  review: "bg-violet-500",
  done: "bg-emerald-500",
  cancelled: "bg-zinc-400",
};

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

// Same gap used by the admin Kanban; large enough to leave room for many
// midpoint inserts before requiring a position rebalance.
const POSITION_GAP = 1000;

function priorityClass(priority: string): string {
  return PRIORITY_CLASSES[priority as TaskPriority] ?? PRIORITY_CLASSES.none;
}

function priorityLabel(priority: string): string {
  return PRIORITY_LABELS[priority as TaskPriority] ?? priority;
}

function stripHtml(value: string): string {
  return value.replace(/<[^>]*>/g, "").trim();
}

function isStateGroup(value: string): value is StateGroup {
  return (GROUP_ORDER as readonly string[]).includes(value);
}

function groupOfTask(
  task: Task,
  stateMap: Record<string, TaskState>,
): StateGroup {
  const state = stateMap[task.state_id];
  if (state && isStateGroup(state.group)) return state.group;
  return "backlog";
}

// Custom collision detection. `closestCorners` (the dnd-kit default for
// kanban examples) skews toward populated columns when the user is hovering
// near an empty column — the empty column has only the droppable container,
// while neighbour columns have many sortable cards whose corners "win" the
// distance test. Result: drop on Cột-Trống lands in Cột-Có-Items next door.
//
// `pointerWithin` returns ONLY droppables whose rect contains the cursor.
// That gives reliable column targeting because every column container is
// the same size and the cursor is always inside exactly one. Fall back to
// `rectIntersection` for edge cases where the cursor briefly leaves all
// rects (fast drag) — this matches the dnd-kit recommended pattern for
// kanban boards with possibly-empty columns.
const collisionDetection: CollisionDetection = (args) => {
  const pointerCollisions = pointerWithin(args);
  if (pointerCollisions.length > 0) return pointerCollisions;
  return rectIntersection(args);
};

function getMoveErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return "Xung đột phiên bản, vui lòng thử lại";
    if (err.message) return err.message;
    return "Không di chuyển được công việc";
  }
  if (err instanceof Error && err.message) return err.message;
  return "Không di chuyển được công việc";
}

export type MyTasksKanbanProps = {
  tasks: Task[];
  // state_id -> TaskState, for resolving each task's group label / chip.
  stateMap: Record<string, TaskState>;
  // project_id -> TaskState[] sorted by position asc. Used to pick the
  // first state in a target group when a card is dropped into a different
  // column. Without this, cross-group drag has no concrete state_id to
  // call moveTask with.
  projectStatesMap: Record<string, TaskState[]>;
  onTaskClick?: (task: Task) => void;
  // Called after a successful drag-to-different-group so the parent can
  // refetch tasks (the task may have moved into/out of a filter — e.g. it
  // hit a terminal `done`/`cancelled` state and the user has the "overdue
  // only" filter turned on).
  onTaskMoved?: () => void;
};

export default function MyTasksKanban({
  tasks: initialTasks,
  stateMap,
  projectStatesMap,
  onTaskClick,
  onTaskMoved,
}: MyTasksKanbanProps) {
  const [tasks, setTasks] = useState<Task[]>(initialTasks);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  // Re-sync internal state when parent refetches. `setTimeout(0)` defers the
  // setState past the synchronous effect body — matches the project's React
  // 19 / `react-hooks/set-state-in-effect` pattern.
  useEffect(() => {
    const timerId = window.setTimeout(() => {
      setTasks(initialTasks);
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [initialTasks]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  // Group tasks by canonical state group, sorted by due_date asc (nulls
  // last) then updated_at desc — same ordering as the list view.
  const tasksByGroup = useMemo(() => {
    const buckets: Record<StateGroup, Task[]> = {
      backlog: [],
      todo: [],
      in_progress: [],
      review: [],
      done: [],
      cancelled: [],
    };
    for (const task of tasks) {
      buckets[groupOfTask(task, stateMap)].push(task);
    }
    for (const key of GROUP_ORDER) {
      buckets[key].sort((a, b) => {
        if (a.due_date && b.due_date) {
          return a.due_date.localeCompare(b.due_date);
        }
        if (a.due_date) return -1;
        if (b.due_date) return 1;
        return b.updated_at.localeCompare(a.updated_at);
      });
    }
    return buckets;
  }, [tasks, stateMap]);

  const handleDragStart = (event: DragStartEvent) => {
    const dragged = tasks.find((t) => t.id === event.active.id);
    if (dragged) {
      setActiveTask(dragged);
      setErrorMessage("");
    }
  };

  const handleDragCancel = () => {
    setActiveTask(null);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveTask(null);
    if (!over) return;

    const dragged = tasks.find((t) => t.id === active.id);
    if (!dragged) return;

    // Resolve target column: `over.id` is either a task id (when dropped
    // over a card) or a group key (when dropped on the column container).
    const overTask = tasks.find((t) => t.id === over.id);
    const overId = over.id as string;
    const targetGroup: StateGroup = overTask
      ? groupOfTask(overTask, stateMap)
      : isStateGroup(overId)
        ? overId
        : "backlog";

    const sourceGroup = groupOfTask(dragged, stateMap);
    const isSameGroup = sourceGroup === targetGroup;
    const targetColumnTasks = tasksByGroup[targetGroup] ?? [];

    // Resolve the actual TaskState we'll send to moveTask.
    //   - Same group: keep the task's existing state_id (no group change).
    //   - Cross group: pick the first state (by position) in the task's
    //     project that matches the target group. Without a match — for
    //     example a personal project that doesn't define a `cancelled`
    //     state — surface an error and bail.
    let targetStateId: string;
    if (isSameGroup) {
      targetStateId = dragged.state_id;
    } else {
      const projectStates = projectStatesMap[dragged.task_project_id] ?? [];
      const match = projectStates.find((s) => s.group === targetGroup);
      if (!match) {
        setErrorMessage(
          `Dự án của công việc này không có trạng thái nhóm "${GROUP_LABELS[targetGroup]}"`,
        );
        return;
      }
      targetStateId = match.id;
    }

    // Compute the new position based on neighbors in the destination column.
    // Same-group moves use a midpoint between adjacent cards; cross-group
    // moves append to the bottom (most natural mental model — the user
    // is reclassifying, not reordering).
    let newPosition: number;
    if (isSameGroup) {
      const sortedColumn = [...targetColumnTasks].sort(
        (a, b) => a.position - b.position,
      );
      const oldIndex = sortedColumn.findIndex((t) => t.id === dragged.id);
      const overIndex = overTask
        ? sortedColumn.findIndex((t) => t.id === overTask.id)
        : sortedColumn.length - 1;
      if (oldIndex === -1 || overIndex === -1 || oldIndex === overIndex) {
        return;
      }
      const reordered = arrayMove(sortedColumn, oldIndex, overIndex);
      const insertIndex = reordered.findIndex((t) => t.id === dragged.id);
      const prev = insertIndex > 0 ? reordered[insertIndex - 1] : null;
      const next =
        insertIndex < reordered.length - 1 ? reordered[insertIndex + 1] : null;
      if (prev && next) {
        newPosition = (prev.position + next.position) / 2;
      } else if (prev) {
        newPosition = prev.position + POSITION_GAP;
      } else if (next) {
        newPosition = next.position - POSITION_GAP;
      } else {
        newPosition = POSITION_GAP;
      }
    } else {
      const lastPosition = targetColumnTasks.reduce(
        (max, t) => (t.position > max ? t.position : max),
        0,
      );
      newPosition = lastPosition + POSITION_GAP;
    }

    // Optimistic update. Roll back on API error so the board doesn't lie.
    const snapshot = tasks;
    const optimistic = tasks.map((t) =>
      t.id === dragged.id
        ? { ...t, state_id: targetStateId, position: newPosition }
        : t,
    );
    setTasks(optimistic);

    try {
      const updated = await moveTask(dragged.id, {
        state_id: targetStateId,
        position: newPosition,
        version: dragged.version,
      });
      setTasks((prev) =>
        prev.map((t) => (t.id === updated.id ? updated : t)),
      );
      // Cross-group moves can change which list filters the task matches
      // (overdue filter ignores `done`/`cancelled` tasks, etc.), so let
      // the parent refetch.
      if (!isSameGroup && onTaskMoved) {
        onTaskMoved();
      }
    } catch (err) {
      setTasks(snapshot);
      setErrorMessage(getMoveErrorMessage(err));
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {errorMessage && (
        <div
          className="flex items-center gap-2 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive"
          role="alert"
          data-testid="my-tasks-kanban-error"
        >
          <span className="material-symbols-outlined text-base">error</span>
          {errorMessage}
        </div>
      )}

      <DndContext
        sensors={sensors}
        collisionDetection={collisionDetection}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
        <div
          className="flex gap-3 overflow-x-auto pb-3"
          data-testid="my-tasks-kanban-board"
        >
          {GROUP_ORDER.map((group) => (
            <KanbanColumn
              key={group}
              group={group}
              tasks={tasksByGroup[group]}
              stateMap={stateMap}
              onTaskClick={onTaskClick}
            />
          ))}
        </div>
        <DragOverlay dropAnimation={null}>
          {activeTask ? (
            <MyTaskCard
              task={activeTask}
              state={stateMap[activeTask.state_id] ?? null}
              isOverlay
            />
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

type KanbanColumnProps = {
  group: StateGroup;
  tasks: Task[];
  stateMap: Record<string, TaskState>;
  onTaskClick?: (task: Task) => void;
};

function KanbanColumn({
  group,
  tasks,
  stateMap,
  onTaskClick,
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: group,
    data: { type: "column", group },
  });

  return (
    <div
      ref={setNodeRef}
      className={`flex w-72 shrink-0 flex-col gap-2 rounded-xl border bg-secondary/30 p-3 transition-colors ${
        isOver
          ? "border-primary/60 bg-primary/5 ring-2 ring-primary/20"
          : "border-border"
      }`}
      data-testid={`my-tasks-kanban-column-${group}`}
    >
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${GROUP_DOT_CLASSES[group]}`}
            aria-hidden
          />
          <span
            className="truncate text-sm font-semibold tracking-tight text-foreground"
            title={GROUP_LABELS[group]}
          >
            {GROUP_LABELS[group]}
          </span>
        </div>
        <span
          className="rounded-full bg-card px-2 py-0.5 text-[11px] font-semibold text-muted-foreground tabular-nums"
          aria-label={`${tasks.length} công việc`}
        >
          {tasks.length}
        </span>
      </div>

      <SortableContext
        id={group}
        items={tasks.map((t) => t.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex min-h-[120px] flex-col gap-2">
          {tasks.length === 0 ? (
            <div className="flex flex-1 items-center justify-center rounded-md border border-dashed border-border/60 bg-card/30 px-3 py-6 text-center text-[11px] text-muted-foreground">
              Thả công việc vào đây
            </div>
          ) : (
            tasks.map((task) => (
              <MyTaskCard
                key={task.id}
                task={task}
                state={stateMap[task.state_id] ?? null}
                onClick={onTaskClick}
              />
            ))
          )}
        </div>
      </SortableContext>
    </div>
  );
}

type MyTaskCardProps = {
  task: Task;
  state: TaskState | null;
  onClick?: (task: Task) => void;
  isOverlay?: boolean;
};

function MyTaskCard({
  task,
  state,
  onClick,
  isOverlay = false,
}: MyTaskCardProps) {
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
  const stateColor = state?.color ?? null;

  return (
    <div
      ref={isOverlay ? undefined : setNodeRef}
      style={style}
      data-testid={`my-task-card-${task.title}`}
      className={`group rounded-lg border border-border bg-card p-3 shadow-sm transition-shadow hover:border-primary/40 hover:shadow-md ${
        isOverlay
          ? "rotate-2 cursor-grabbing shadow-lg"
          : "cursor-grab active:cursor-grabbing"
      }`}
      {...(isOverlay ? {} : attributes)}
      {...(isOverlay ? {} : listeners)}
      onClick={(event) => {
        if (isOverlay) return;
        // dnd-kit fires a synthetic click after a drag — guard against it.
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
          {state && (
            <span
              className="inline-flex items-center gap-1 text-[10px] text-muted-foreground"
              title={`Trạng thái: ${translateStateName(state.name)}`}
            >
              <span
                className="h-1.5 w-1.5 rounded-full bg-primary"
                style={stateColor ? { backgroundColor: stateColor } : undefined}
                aria-hidden
              />
              {translateStateName(state.name)}
            </span>
          )}
          {task.due_date && (
            <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground tabular-nums">
              <span className="material-symbols-outlined text-[12px]">
                event
              </span>
              {formatTaskDate(task.due_date)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
