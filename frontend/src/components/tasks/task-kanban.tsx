"use client";

import { useEffect, useState } from "react";
import {
  DndContext,
  type DragEndEvent,
  type DragStartEvent,
  DragOverlay,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { ApiError } from "@/lib/api";
import { moveTask } from "@/lib/task-api";
import type { Task, TaskState } from "@/lib/task-types";
import { translateStateName } from "@/lib/task-i18n";
import { TaskCard } from "@/components/tasks/task-card";

const POSITION_GAP = 1000;

export type TaskKanbanProps = {
  initialTasks: Task[];
  states: TaskState[];
  onTaskClick?: (task: Task) => void;
};

function getMoveErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return "xung đột phiên bản";
    if (err.message) return err.message;
    return "Không di chuyển được công việc";
  }
  if (err instanceof Error && err.message) return err.message;
  return "Không di chuyển được công việc";
}

export default function TaskKanban({
  initialTasks,
  states,
  onTaskClick,
}: TaskKanbanProps) {
  const [tasks, setTasks] = useState<Task[]>(initialTasks);
  const [errorMessage, setErrorMessage] = useState("");
  const [activeTask, setActiveTask] = useState<Task | null>(null);

  // Re-sync internal state when parent reloads tasks (filter change, post-mutation refetch).
  // Uses setTimeout pattern to avoid `react-hooks/set-state-in-effect`.
  useEffect(() => {
    const timerId = window.setTimeout(() => {
      setTasks(initialTasks);
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [initialTasks]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    })
  );

  const sortedStates = [...states].sort((a, b) => a.position - b.position);

  // Group tasks by state and sort by position within each column.
  const tasksByState: Record<string, Task[]> = {};
  for (const state of sortedStates) {
    tasksByState[state.id] = [];
  }
  for (const task of tasks) {
    if (!tasksByState[task.state_id]) {
      tasksByState[task.state_id] = [];
    }
    tasksByState[task.state_id].push(task);
  }
  for (const stateId of Object.keys(tasksByState)) {
    tasksByState[stateId].sort((a, b) => a.position - b.position);
  }

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

    // Resolve target column: `over.id` is either a task ID (when dropped over a card)
    // or a state ID (when dropped on an empty column container).
    const overTask = tasks.find((t) => t.id === over.id);
    const targetStateId = overTask ? overTask.state_id : (over.id as string);
    if (!sortedStates.some((s) => s.id === targetStateId)) return;

    const isSameColumn = dragged.state_id === targetStateId;
    const targetColumnTasks = tasksByState[targetStateId] ?? [];

    // Compute the new position based on the post-move neighbor positions in the
    // destination column. Cross-column appends to the end; same-column inserts
    // at the over-card's index using the midpoint between neighbours.
    let newPosition: number;
    if (isSameColumn) {
      const sortedColumn = [...targetColumnTasks].sort(
        (a, b) => a.position - b.position
      );
      const oldIndex = sortedColumn.findIndex((t) => t.id === dragged.id);
      const overIndex = overTask
        ? sortedColumn.findIndex((t) => t.id === overTask.id)
        : sortedColumn.length - 1;
      // No-op: dropped on itself or on the same slot it already occupies.
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
      // Cross-column: append to the bottom of the destination column.
      const lastPosition = targetColumnTasks.reduce(
        (max, t) => (t.position > max ? t.position : max),
        0
      );
      newPosition = lastPosition + POSITION_GAP;
    }

    const snapshot = tasks;
    const optimistic = tasks.map((t) =>
      t.id === dragged.id
        ? { ...t, state_id: targetStateId, position: newPosition }
        : t
    );
    setTasks(optimistic);

    try {
      const updated = await moveTask(dragged.id, {
        state_id: targetStateId,
        position: newPosition,
        version: dragged.version,
      });
      setTasks((prev) =>
        prev.map((t) => (t.id === updated.id ? updated : t))
      );
    } catch (err) {
      // Rollback to snapshot, surface inline error message.
      setTasks(snapshot);
      setErrorMessage(getMoveErrorMessage(err));
    }
  };

  if (sortedStates.length === 0) {
    return (
      <div
        className="rounded-xl border border-dashed border-border bg-card/40 p-8 text-center text-sm text-muted-foreground"
        data-testid="task-kanban-empty-states"
      >
        Chưa có trạng thái nào trong dự án này.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {errorMessage && (
        <div
          className="flex items-center gap-2 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive"
          role="alert"
          data-testid="task-kanban-error"
        >
          <span className="material-symbols-outlined text-base">error</span>
          {errorMessage}
        </div>
      )}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
        <div
          className="flex gap-3 overflow-x-auto pb-3"
          data-testid="task-kanban-board"
        >
          {sortedStates.map((state) => (
            <KanbanColumn
              key={state.id}
              state={state}
              tasks={tasksByState[state.id] ?? []}
              onTaskClick={onTaskClick}
            />
          ))}
        </div>
        <DragOverlay dropAnimation={null}>
          {activeTask ? <TaskCard task={activeTask} isOverlay /> : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

type KanbanColumnProps = {
  state: TaskState;
  tasks: Task[];
  onTaskClick?: (task: Task) => void;
};

function KanbanColumn({ state, tasks, onTaskClick }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: state.id,
    data: { type: "column", stateId: state.id },
  });

  const accent = state.color ?? undefined;
  const displayName = translateStateName(state.name);

  return (
    <div
      ref={setNodeRef}
      className={`flex w-72 shrink-0 flex-col gap-2 rounded-xl border bg-secondary/30 p-3 transition-colors ${
        isOver
          ? "border-primary/60 bg-primary/5 ring-2 ring-primary/20"
          : "border-border"
      }`}
      data-testid={`task-kanban-column-${state.name}`}
    >
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className="h-2 w-2 shrink-0 rounded-full bg-primary"
            style={accent ? { backgroundColor: accent } : undefined}
            aria-hidden
          />
          <span
            className="truncate text-sm font-semibold tracking-tight text-foreground"
            title={displayName}
          >
            {displayName}
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
        id={state.id}
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
              <TaskCard key={task.id} task={task} onClick={onTaskClick} />
            ))
          )}
        </div>
      </SortableContext>
    </div>
  );
}
