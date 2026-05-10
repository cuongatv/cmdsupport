"use client";

import React from "react";
import type {
  EligibleAssignee,
  TaskLabel,
  TaskPriority,
  TaskProject,
  TaskState,
} from "@/lib/task-types";
import { translateStateName } from "@/lib/task-i18n";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

export const TASK_FILTER_ALL_VALUE = "__all__";
export type TaskScopeFilter = "" | "all" | "workspace" | "department";

const SCOPE_OPTIONS: Array<{ value: TaskScopeFilter; label: string }> = [
  { value: "", label: "Tất cả phạm vi" },
  { value: "workspace", label: "Theo workspace" },
  { value: "department", label: "Theo phòng ban" },
];

export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  none: "Không có",
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  urgent: "Khẩn cấp",
};

const PRIORITY_OPTIONS: Array<{ value: TaskPriority; label: string }> = [
  { value: "none", label: TASK_PRIORITY_LABELS.none },
  { value: "low", label: TASK_PRIORITY_LABELS.low },
  { value: "medium", label: TASK_PRIORITY_LABELS.medium },
  { value: "high", label: TASK_PRIORITY_LABELS.high },
  { value: "urgent", label: TASK_PRIORITY_LABELS.urgent },
];

export type TaskListFilterValues = {
  task_project_id: string;
  state_id: string;
  priority: string;
  assignee_id: string;
  reporter_id: string;
  label_id: string;
  due_after: string;
  due_before: string;
  overdue: boolean;
  scope: TaskScopeFilter;
  search: string;
};

type TaskListFiltersProps = {
  projects: TaskProject[];
  states: TaskState[];
  assignees: EligibleAssignee[];
  labels: TaskLabel[];
  values: TaskListFilterValues;
  scopedFiltersDisabled: boolean;
  showScopeFilter: boolean;
  onProjectChange: (projectId: string) => void;
  onStateChange: (stateId: string) => void;
  onPriorityChange: (priority: string) => void;
  onAssigneeChange: (assigneeId: string) => void;
  onReporterChange: (reporterId: string) => void;
  onLabelChange: (labelId: string) => void;
  onDueAfterChange: (date: string) => void;
  onDueBeforeChange: (date: string) => void;
  onOverdueChange: (overdue: boolean) => void;
  onScopeChange: (scope: TaskScopeFilter) => void;
  onSearchSubmit: (query: string) => void;
};

function toSelectValue(value: string): string {
  return value || TASK_FILTER_ALL_VALUE;
}

function fromSelectValue(value: string): string {
  return value === TASK_FILTER_ALL_VALUE ? "" : value;
}

// Compact field-label class shared across every dropdown in the filter bar.
// Smaller weight than the form-dialog `<Label>` default keeps the bar dense.
const FILTER_LABEL_CLASS =
  "text-xs font-medium text-muted-foreground tracking-wide";

export function TaskListFilters({
  projects,
  states,
  assignees,
  labels,
  values,
  scopedFiltersDisabled,
  showScopeFilter,
  onProjectChange,
  onStateChange,
  onPriorityChange,
  onAssigneeChange,
  onReporterChange,
  onLabelChange,
  onDueAfterChange,
  onDueBeforeChange,
  onOverdueChange,
  onScopeChange,
  onSearchSubmit,
}: TaskListFiltersProps) {
  const [searchInput, setSearchInput] = React.useState(values.search);

  // Resolve the display name for the currently-selected option in each
  // dropdown. Plain `const` (no `useMemo`) keeps the React Compiler happy and
  // these lookups are O(n) over very small arrays. The string is also used as
  // the `title` attribute so the full text is reachable on hover when the
  // trigger truncates.
  const selectedProject = projects.find(
    (p) => p.id === values.task_project_id
  );
  const selectedProjectName = selectedProject?.name ?? "";

  const selectedState = states.find((s) => s.id === values.state_id);
  const selectedStateLabel = selectedState
    ? translateStateName(selectedState.name)
    : "";

  const selectedPriorityOption = PRIORITY_OPTIONS.find(
    (option) => option.value === values.priority
  );
  const selectedPriorityLabel = selectedPriorityOption?.label ?? "";

  const selectedAssignee = assignees.find((a) => a.id === values.assignee_id);
  const selectedAssigneeName = selectedAssignee?.name ?? "";

  const selectedReporter = assignees.find((a) => a.id === values.reporter_id);
  const selectedReporterName = selectedReporter?.name ?? "";

  const selectedLabel = labels.find((l) => l.id === values.label_id);
  const selectedLabelName = selectedLabel?.name ?? "";

  const handleSearchSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    onSearchSubmit(searchInput.trim());
  };

  const handleClearSearch = () => {
    setSearchInput("");
    onSearchSubmit("");
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-end">
        <form
          onSubmit={handleSearchSubmit}
          className="md:order-1 flex flex-col gap-1"
        >
          <Label htmlFor="task-filter-search" className={FILTER_LABEL_CLASS}>
            Tìm kiếm
          </Label>
          <div className="relative">
            <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">
              search
            </span>
            <input
              id="task-filter-search"
              type="text"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Tìm kiếm..."
              className="h-9 w-full md:w-[260px] rounded-lg border border-border bg-background pl-9 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 placeholder:text-muted-foreground/60"
              data-testid="task-filter-search"
            />
            {searchInput && (
              <button
                type="button"
                onClick={handleClearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                aria-label="Xoá tìm kiếm"
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            )}
          </div>
        </form>

        <div className="flex flex-col gap-2 md:order-2 md:flex-row md:flex-wrap md:items-end">
          <div className="flex flex-col gap-1">
            <Label
              htmlFor="task-filter-project"
              className={FILTER_LABEL_CLASS}
            >
              Dự án
            </Label>
            <Select
              value={toSelectValue(values.task_project_id)}
              onValueChange={(next) =>
                onProjectChange(fromSelectValue(next ?? TASK_FILTER_ALL_VALUE))
              }
            >
              <SelectTrigger
                id="task-filter-project"
                className="w-full md:w-[200px] bg-background"
                data-testid="task-filter-project"
              >
                {selectedProjectName ? (
                  <span
                    className="truncate max-w-[160px]"
                    title={selectedProjectName}
                  >
                    {selectedProjectName}
                  </span>
                ) : (
                  <SelectValue placeholder="Tất cả dự án" />
                )}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TASK_FILTER_ALL_VALUE}>
                  Tất cả dự án
                </SelectItem>
                {projects.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-muted-foreground">
                    Chưa có dự án nào
                  </div>
                ) : (
                  projects.map((project) => (
                    <SelectItem key={project.id} value={project.id}>
                      <span className="truncate">{project.name}</span>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1">
            <Label htmlFor="task-filter-state" className={FILTER_LABEL_CLASS}>
              Trạng thái xử lý
            </Label>
            <Select
              value={toSelectValue(values.state_id)}
              onValueChange={(next) =>
                onStateChange(fromSelectValue(next ?? TASK_FILTER_ALL_VALUE))
              }
              disabled={scopedFiltersDisabled}
            >
              <SelectTrigger
                id="task-filter-state"
                className="w-full md:w-[180px] bg-background"
                data-testid="task-filter-state"
              >
                {selectedStateLabel ? (
                  <span
                    className="truncate max-w-[140px]"
                    title={selectedStateLabel}
                  >
                    {selectedStateLabel}
                  </span>
                ) : (
                  <SelectValue placeholder="Tất cả trạng thái" />
                )}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TASK_FILTER_ALL_VALUE}>
                  Tất cả trạng thái
                </SelectItem>
                {states.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-muted-foreground">
                    Chọn dự án để xem trạng thái
                  </div>
                ) : (
                  states.map((state) => (
                    <SelectItem key={state.id} value={state.id}>
                      <span className="truncate">
                        {translateStateName(state.name)}
                      </span>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1">
            <Label
              htmlFor="task-filter-priority"
              className={FILTER_LABEL_CLASS}
            >
              Mức độ ưu tiên
            </Label>
            <Select
              value={toSelectValue(values.priority)}
              onValueChange={(next) =>
                onPriorityChange(fromSelectValue(next ?? TASK_FILTER_ALL_VALUE))
              }
            >
              <SelectTrigger
                id="task-filter-priority"
                className="w-full md:w-[160px] bg-background"
                data-testid="task-filter-priority"
              >
                {selectedPriorityLabel ? (
                  <span
                    className="truncate max-w-[120px]"
                    title={selectedPriorityLabel}
                  >
                    {selectedPriorityLabel}
                  </span>
                ) : (
                  <SelectValue placeholder="Tất cả ưu tiên" />
                )}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TASK_FILTER_ALL_VALUE}>
                  Tất cả ưu tiên
                </SelectItem>
                {PRIORITY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1">
            <Label
              htmlFor="task-filter-assignee"
              className={FILTER_LABEL_CLASS}
            >
              Người phụ trách
            </Label>
            <Select
              value={toSelectValue(values.assignee_id)}
              onValueChange={(next) =>
                onAssigneeChange(fromSelectValue(next ?? TASK_FILTER_ALL_VALUE))
              }
              disabled={scopedFiltersDisabled}
            >
              <SelectTrigger
                id="task-filter-assignee"
                className="w-full md:w-[200px] bg-background"
                data-testid="task-filter-assignee"
              >
                {selectedAssigneeName ? (
                  <span
                    className="truncate max-w-[160px]"
                    title={selectedAssigneeName}
                  >
                    {selectedAssigneeName}
                  </span>
                ) : (
                  <SelectValue placeholder="Tất cả người nhận" />
                )}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TASK_FILTER_ALL_VALUE}>
                  Tất cả người nhận
                </SelectItem>
                {assignees.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-muted-foreground">
                    Chọn dự án để xem người nhận
                  </div>
                ) : (
                  assignees.map((assignee) => (
                    <SelectItem key={assignee.id} value={assignee.id}>
                      <div className="flex flex-col">
                        <span className="truncate">{assignee.name}</span>
                        <span className="text-[11px] text-muted-foreground truncate">
                          {assignee.email}
                        </span>
                      </div>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-end">
        <div className="flex flex-col gap-1">
          <Label htmlFor="task-filter-reporter" className={FILTER_LABEL_CLASS}>
            Người báo cáo
          </Label>
          <Select
            value={toSelectValue(values.reporter_id)}
            onValueChange={(next) =>
              onReporterChange(fromSelectValue(next ?? TASK_FILTER_ALL_VALUE))
            }
            disabled={scopedFiltersDisabled}
          >
            <SelectTrigger
              id="task-filter-reporter"
              className="w-full md:w-[200px] bg-background"
              data-testid="task-filter-reporter"
            >
              {selectedReporterName ? (
                <span
                  className="truncate max-w-[160px]"
                  title={selectedReporterName}
                >
                  {selectedReporterName}
                </span>
              ) : (
                <SelectValue placeholder="Tất cả người báo cáo" />
              )}
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TASK_FILTER_ALL_VALUE}>
                Tất cả người báo cáo
              </SelectItem>
              {assignees.length === 0 ? (
                <div className="px-3 py-2 text-xs text-muted-foreground">
                  Chọn dự án để xem người báo cáo
                </div>
              ) : (
                assignees.map((assignee) => (
                  <SelectItem key={assignee.id} value={assignee.id}>
                    <div className="flex flex-col">
                      <span className="truncate">{assignee.name}</span>
                      <span className="text-[11px] text-muted-foreground truncate">
                        {assignee.email}
                      </span>
                    </div>
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <Label htmlFor="task-filter-label" className={FILTER_LABEL_CLASS}>
            Nhãn
          </Label>
          <Select
            value={toSelectValue(values.label_id)}
            onValueChange={(next) =>
              onLabelChange(fromSelectValue(next ?? TASK_FILTER_ALL_VALUE))
            }
            disabled={scopedFiltersDisabled}
          >
            <SelectTrigger
              id="task-filter-label"
              className="w-full md:w-[200px] bg-background"
              data-testid="task-filter-label"
            >
              {selectedLabelName ? (
                <span
                  className="truncate max-w-[160px]"
                  title={selectedLabelName}
                >
                  {selectedLabelName}
                </span>
              ) : (
                <SelectValue placeholder="Tất cả nhãn" />
              )}
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={TASK_FILTER_ALL_VALUE}>Tất cả nhãn</SelectItem>
              {labels.length === 0 ? (
                <div className="px-3 py-2 text-xs text-muted-foreground">
                  Chưa có nhãn nào trong dự án này
                </div>
              ) : (
                labels.map((label) => (
                  <SelectItem key={label.id} value={label.id}>
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 shrink-0 rounded-full bg-primary"
                        style={
                          label.color
                            ? { backgroundColor: label.color }
                            : undefined
                        }
                        aria-hidden
                      />
                      <span className="truncate">{label.name}</span>
                    </div>
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </div>

        <label className="flex h-9 items-center gap-2 self-end rounded-lg border border-border bg-background px-3 text-sm text-foreground">
          <span className="text-xs text-muted-foreground">Hạn từ</span>
          <input
            type="date"
            value={values.due_after}
            onChange={(event) => onDueAfterChange(event.target.value)}
            className="bg-transparent text-xs focus:outline-none"
            data-testid="task-filter-due-after"
            aria-label="Hạn từ ngày"
          />
        </label>

        <label className="flex h-9 items-center gap-2 self-end rounded-lg border border-border bg-background px-3 text-sm text-foreground">
          <span className="text-xs text-muted-foreground">Hạn đến</span>
          <input
            type="date"
            value={values.due_before}
            onChange={(event) => onDueBeforeChange(event.target.value)}
            className="bg-transparent text-xs focus:outline-none"
            data-testid="task-filter-due-before"
            aria-label="Hạn đến ngày"
          />
        </label>

        <label className="flex h-9 cursor-pointer items-center gap-2 self-end rounded-lg border border-border bg-background px-3 text-sm text-foreground hover:bg-muted/50 transition-colors">
          <Checkbox
            checked={values.overdue}
            onCheckedChange={(checked) => onOverdueChange(Boolean(checked))}
            data-testid="task-filter-overdue"
          />
          <span className="text-xs">Chỉ hiển thị quá hạn</span>
        </label>

        {showScopeFilter && (
          <div className="flex flex-col gap-1">
            <span
              id="task-filter-scope-label"
              className={FILTER_LABEL_CLASS}
            >
              Phạm vi
            </span>
            <div
              className="inline-flex h-9 items-center rounded-lg border border-border bg-background p-0.5"
              role="radiogroup"
              aria-labelledby="task-filter-scope-label"
              data-testid="task-filter-scope"
            >
              {SCOPE_OPTIONS.map((option) => {
                const isActive = values.scope === option.value;
                return (
                  <button
                    key={option.value || "all"}
                    type="button"
                    role="radio"
                    aria-checked={isActive}
                    onClick={() => onScopeChange(option.value)}
                    data-testid={`task-filter-scope-${option.value || "all"}`}
                    className={`inline-flex h-7 items-center rounded-md px-3 text-xs font-medium transition-colors ${
                      isActive
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    }`}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
