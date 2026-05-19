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
import { FEATURE_AGILE_PHASE_1, FEATURE_AGILE_PHASE_5 } from "@/lib/feature-flags";
import { moveTask } from "@/lib/task-api";
import type {
  Task,
  TaskGovernanceAdvisory,
  TaskMoveAdvisory,
  TaskState,
} from "@/lib/task-types";
import { translateStateName } from "@/lib/task-i18n";
import { TaskCard } from "@/components/tasks/task-card";
import { TaskStateSettingsDialog } from "@/components/tasks/task-state-settings-dialog";
import { GovernanceAdvisoryToast } from "@/components/tasks/governance-advisory-toast";

const POSITION_GAP = 1000;

export type TaskKanbanProps = {
  initialTasks: Task[];
  states: TaskState[];
  onTaskClick?: (task: Task) => void;
  /**
   * Multi-project mode: `states` are virtual canonical-group columns
   * (one per backlog/todo/in_progress/…). Tasks are routed to a column
   * via `realStateMap[task.state_id].group`. Drag-and-drop is disabled
   * because `state_id` is per-project, so cross-project moves have no
   * unambiguous target.
   */
  groupedView?: boolean;
  /** Real per-project TaskState lookup, used only when `groupedView=true`. */
  realStateMap?: Record<string, TaskState>;
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
  groupedView = false,
  realStateMap,
}: TaskKanbanProps) {
  const [tasks, setTasks] = useState<Task[]>(initialTasks);
  const [errorMessage, setErrorMessage] = useState("");
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  // Phase 1: WIP advisory toast surfaced when backend returns `warn` policy
  // on a successful move. Distinct from `errorMessage` (which is for hard
  // failures) so the move itself is NOT rolled back.
  const [advisory, setAdvisory] = useState<TaskMoveAdvisory | null>(null);
  // Phase 5: Stage A governance advisories from the same move response.
  // Multiple advisories can fire on a single move (e.g. WIP + DoD bypass).
  // Independent of `advisory` above so the WIP and governance toasts can
  // coexist on the same column drop.
  const [governanceAdvisories, setGovernanceAdvisories] = useState<
    TaskGovernanceAdvisory[]
  >([]);
  // Phase 1: per-column WIP / aging settings dialog. Local mirror of the
  // states prop so the dialog's onSaved patch sticks until the parent
  // refetches.
  const [localStates, setLocalStates] = useState<TaskState[]>(states);
  const [settingsStateId, setSettingsStateId] = useState<string | null>(null);

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      setLocalStates(states);
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [states]);

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

  const sortedStates = [...localStates].sort((a, b) => a.position - b.position);

  // Column key strategy depends on mode. Single-project: column key is the
  // real `state.id` and a task lands in its column when `task.state_id` matches.
  // Grouped (multi-project) mode: column key is `state.group` (canonical) and
  // each task is routed via `realStateMap[task.state_id].group` so all the
  // per-project "Backlog" rows collapse into one column.
  const columnKey = (s: TaskState): string =>
    groupedView ? s.group : s.id;
  const taskColumnKey = (task: Task): string | null => {
    if (!groupedView) return task.state_id;
    const real = realStateMap?.[task.state_id];
    return real ? real.group : null;
  };

  // Group tasks by column key and sort by position within each column.
  const tasksByState: Record<string, Task[]> = {};
  for (const state of sortedStates) {
    tasksByState[columnKey(state)] = [];
  }
  for (const task of tasks) {
    const key = taskColumnKey(task);
    if (key === null) continue;
    if (!tasksByState[key]) {
      tasksByState[key] = [];
    }
    tasksByState[key].push(task);
  }
  for (const key of Object.keys(tasksByState)) {
    tasksByState[key].sort((a, b) => a.position - b.position);
  }

  const handleDragStart = (event: DragStartEvent) => {
    const dragged = tasks.find((t) => t.id === event.active.id);
    if (dragged) {
      setActiveTask(dragged);
      setErrorMessage("");
      setAdvisory(null);
      setGovernanceAdvisories([]);
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
      const result = await moveTask(dragged.id, {
        state_id: targetStateId,
        position: newPosition,
        version: dragged.version,
      });
      setTasks((prev) =>
        prev.map((t) => (t.id === result.task.id ? result.task : t))
      );
      // Phase 1: surface a non-blocking advisory toast when backend returns
      // `warn` policy. The move itself succeeded — we DO NOT roll back.
      if (FEATURE_AGILE_PHASE_1 && result.advisory) {
        setAdvisory(result.advisory);
      } else {
        setAdvisory(null);
      }
      // Phase 5: surface the governance advisory toast alongside the WIP
      // one. The move succeeded; the toast is purely a permission breadcrumb.
      if (FEATURE_AGILE_PHASE_5 && result.governance_advisories.length > 0) {
        setGovernanceAdvisories(result.governance_advisories);
      } else {
        setGovernanceAdvisories([]);
      }
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

  const settingsState =
    settingsStateId !== null
      ? localStates.find((s) => s.id === settingsStateId) ?? null
      : null;

  const handleStateSaved = (updated: TaskState) => {
    setLocalStates((prev) =>
      prev.map((s) => (s.id === updated.id ? updated : s)),
    );
  };

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

      <GovernanceAdvisoryToast
        advisories={governanceAdvisories}
        onDismiss={() => setGovernanceAdvisories([])}
      />

      {FEATURE_AGILE_PHASE_1 && advisory && (
        <div
          className="flex items-start justify-between gap-3 rounded-lg border border-amber-300/70 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-400/40 dark:bg-amber-950/30 dark:text-amber-100"
          role="status"
          data-testid="agile-advisory-toast"
        >
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-base">warning</span>
            <div className="flex flex-col gap-0.5">
              <span className="font-medium">
                Cảnh báo khuyến nghị: vượt giới hạn việc đang làm
              </span>
              <span className="text-xs text-amber-800/90 dark:text-amber-100/80">
                Cột hiện có {advisory.current_count} công việc, vượt giới hạn{" "}
                {advisory.wip_limit}. Bạn vẫn có thể tiếp tục — đây chỉ là cảnh
                báo.
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setAdvisory(null)}
            className="rounded-md p-1 text-amber-700 hover:bg-amber-100 dark:text-amber-200 dark:hover:bg-amber-900/40"
            aria-label="Đóng cảnh báo"
            data-testid="agile-advisory-toast-dismiss"
          >
            <span className="material-symbols-outlined text-sm">close</span>
          </button>
        </div>
      )}

      {groupedView && (
        <div
          className="flex items-start gap-2 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-xs text-muted-foreground"
          role="status"
        >
          <span className="material-symbols-outlined text-[16px] mt-0.5">
            info
          </span>
          <span>
            Đang xem nhiều dự án — các cột được gộp theo nhóm trạng thái chung.
            Để kéo-thả công việc, hãy chọn một dự án cụ thể ở bộ lọc.
          </span>
        </div>
      )}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={groupedView ? undefined : handleDragStart}
        onDragEnd={groupedView ? undefined : handleDragEnd}
        onDragCancel={groupedView ? undefined : handleDragCancel}
      >
        <div
          className="flex gap-3 overflow-x-auto pb-3"
          data-testid="task-kanban-board"
        >
          {sortedStates.map((state) => (
            <KanbanColumn
              key={columnKey(state)}
              state={state}
              tasks={tasksByState[columnKey(state)] ?? []}
              onTaskClick={onTaskClick}
              droppableId={columnKey(state)}
              dragDisabled={groupedView}
              onOpenSettings={
                FEATURE_AGILE_PHASE_1 && !groupedView
                  ? () => setSettingsStateId(state.id)
                  : undefined
              }
            />
          ))}
        </div>
        <DragOverlay dropAnimation={null}>
          {activeTask ? <TaskCard task={activeTask} isOverlay /> : null}
        </DragOverlay>
      </DndContext>

      {FEATURE_AGILE_PHASE_1 && settingsState && (
        <TaskStateSettingsDialog
          key={settingsState.id}
          open={true}
          onOpenChange={(open) => {
            if (!open) setSettingsStateId(null);
          }}
          state={settingsState}
          onSaved={handleStateSaved}
        />
      )}
    </div>
  );
}

type KanbanColumnProps = {
  state: TaskState;
  tasks: Task[];
  onTaskClick?: (task: Task) => void;
  onOpenSettings?: () => void;
  /** Override the droppable id (used in grouped multi-project mode). */
  droppableId?: string;
  /** When true, the column does not accept drops (no cross-project move). */
  dragDisabled?: boolean;
};

function KanbanColumn({
  state,
  tasks,
  onTaskClick,
  onOpenSettings,
  droppableId,
  dragDisabled = false,
}: KanbanColumnProps) {
  const id = droppableId ?? state.id;
  const { setNodeRef, isOver } = useDroppable({
    id,
    data: { type: "column", stateId: id },
    disabled: dragDisabled,
  });

  const accent = state.color ?? undefined;
  const displayName = translateStateName(state.name);
  // Phase 1: surface WIP usage as `count / limit` next to the column name when
  // the column has a configured limit. Pure visual hint — enforcement happens
  // server-side via wip_policy.
  const wipLimit = state.wip_limit ?? null;
  const overLimit = wipLimit !== null && wipLimit > 0 && tasks.length > wipLimit;

  return (
    <div
      ref={setNodeRef}
      className={`flex w-72 shrink-0 flex-col gap-2 rounded-xl border bg-secondary/30 p-3 transition-colors ${
        isOver
          ? "border-primary/60 bg-primary/5 ring-2 ring-primary/20"
          : "border-border"
      }`}
      data-testid={`task-kanban-column-${id}`}
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
        <div className="flex items-center gap-1">
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${
              overLimit
                ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-100"
                : "bg-card text-muted-foreground"
            }`}
            aria-label={`${tasks.length} công việc${
              wipLimit !== null ? `, giới hạn ${wipLimit}` : ""
            }`}
          >
            {wipLimit !== null && wipLimit > 0
              ? `${tasks.length} / ${wipLimit}`
              : tasks.length}
          </span>
          {onOpenSettings && (
            <button
              type="button"
              onClick={onOpenSettings}
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-card hover:text-foreground"
              aria-label={`Cấu hình Kanban cho cột ${displayName}`}
              title="Cấu hình Kanban"
              data-testid="task-state-settings-btn"
            >
              <span className="material-symbols-outlined text-sm">
                settings
              </span>
            </button>
          )}
        </div>
      </div>

      <SortableContext
        id={id}
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
