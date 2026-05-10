"use client";

import React from "react";
import { ApiError } from "@/lib/api";
import { listTaskActivities } from "@/lib/task-api";
import type {
  EligibleAssignee,
  TaskActivity,
  TaskState,
} from "@/lib/task-types";
import { formatTaskDateTime } from "@/lib/task-types";
import { translateStateName } from "@/lib/task-i18n";

const VERB_LABELS: Record<string, string> = {
  commented: "đã bình luận",
  comment_edited: "đã chỉnh sửa bình luận",
  comment_deleted: "đã xóa bình luận",
  attachment_added: "đã đính kèm tệp",
  attachment_removed: "đã gỡ tệp đính kèm",
  state_changed: "đã đổi trạng thái",
  assigned: "đã được giao việc",
  unassigned: "đã được gỡ giao việc",
};

const FIELD_LABELS: Record<string, string> = {
  title: "tiêu đề",
  description: "mô tả",
  priority: "mức ưu tiên",
  due_date: "ngày hết hạn",
  reporter_id: "người báo cáo",
  parent_task_id: "công việc cha",
  state_id: "trạng thái",
};

const VERB_ICONS: Record<string, string> = {
  commented: "chat",
  comment_edited: "edit_note",
  comment_deleted: "delete_sweep",
  attachment_added: "attach_file",
  attachment_removed: "scan_delete",
  state_changed: "swap_horiz",
  assigned: "person_add",
  unassigned: "person_remove",
};

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function verbIcon(verb: string): string {
  return VERB_ICONS[verb] ?? "history";
}

function verbLabel(verb: string, fieldName: string | null): string {
  const direct = VERB_LABELS[verb];
  if (direct) return direct;
  // Generic field-level update verb (e.g. "title_changed").
  if (verb.endsWith("_changed")) {
    const field = verb.slice(0, -"_changed".length);
    const friendly = FIELD_LABELS[field] ?? fieldName ?? field;
    return `đã cập nhật ${friendly}`;
  }
  return "đã cập nhật công việc";
}

function detailText(
  activity: TaskActivity,
  stateLookup: Record<string, TaskState>,
  employeeLookup: Record<string, EligibleAssignee>
): string {
  const meta = activity.meta as Record<string, unknown> | null;
  const verb = activity.verb;

  if (verb === "state_changed" && meta) {
    const oldName =
      (meta.old_state_name as string | undefined) ??
      (typeof meta.old_state_id === "string"
        ? stateLookup[meta.old_state_id]?.name
        : undefined) ??
      activity.old_value ??
      "";
    const newName =
      (meta.new_state_name as string | undefined) ??
      (typeof meta.new_state_id === "string"
        ? stateLookup[meta.new_state_id]?.name
        : undefined) ??
      activity.new_value ??
      "";
    const oldLabel = translateStateName(oldName);
    const newLabel = translateStateName(newName);
    if (oldLabel && newLabel) return `${oldLabel} → ${newLabel}`;
    if (newLabel) return newLabel;
  }

  if (
    (verb === "attachment_added" || verb === "attachment_removed") &&
    meta &&
    typeof meta.filename === "string"
  ) {
    return meta.filename;
  }

  if ((verb === "assigned" || verb === "unassigned") && meta) {
    const targetId = meta.employee_id;
    if (typeof targetId === "string" && employeeLookup[targetId]) {
      return employeeLookup[targetId].name;
    }
  }

  if (activity.old_value && activity.new_value) {
    return `${activity.old_value} → ${activity.new_value}`;
  }
  if (activity.new_value) return activity.new_value;
  return "";
}

export type TaskActivityFeedProps = {
  taskId: string;
  eligibleAssignees: EligibleAssignee[];
  states: TaskState[];
};

export function TaskActivityFeed({
  taskId,
  eligibleAssignees,
  states,
}: TaskActivityFeedProps) {
  const [activities, setActivities] = React.useState<TaskActivity[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const employeeMap = Object.fromEntries(
    eligibleAssignees.map((e) => [e.id, e])
  );
  const stateMap = Object.fromEntries(states.map((s) => [s.id, s]));

  const loadActivities = React.useCallback(async () => {
    setLoading(true);
    try {
      const data = await listTaskActivities(taskId);
      setActivities(data);
      setError("");
    } catch (err) {
      setActivities([]);
      setError(getErrorMessage(err, "Không tải được dòng hoạt động"));
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  React.useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadActivities();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadActivities]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <span className="material-symbols-outlined text-2xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <p
        className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg"
        role="alert"
        data-testid="task-activity-error"
      >
        {error}
      </p>
    );
  }

  if (activities.length === 0) {
    return (
      <p className="text-xs text-muted-foreground text-center py-6">
        Chưa có hoạt động nào.
      </p>
    );
  }

  return (
    <ul
      className="flex flex-col gap-2"
      data-testid="task-activity-list"
    >
      {activities.map((a) => {
        const actor = a.actor_id ? employeeMap[a.actor_id] : null;
        const detail = detailText(a, stateMap, employeeMap);
        return (
          <li
            key={a.id}
            className="flex items-start gap-2.5 rounded-lg border border-border bg-background px-3 py-2"
            data-testid={`task-activity-${a.id}`}
          >
            <span className="material-symbols-outlined text-base text-muted-foreground mt-0.5">
              {verbIcon(a.verb)}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-1.5 text-sm">
                <span className="font-medium text-foreground">
                  {actor?.name ?? "Hệ thống"}
                </span>
                <span className="text-muted-foreground">
                  {verbLabel(a.verb, a.field_name)}
                </span>
                {detail && (
                  <span className="text-foreground truncate">{detail}</span>
                )}
              </div>
              <span className="text-[11px] text-muted-foreground tabular-nums">
                {formatTaskDateTime(a.created_at)}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
