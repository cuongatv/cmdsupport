"""Frozen constants for the native task domain.

TaskProject is a new domain model. The existing Project model remains the
workspace model and must not be repurposed for task-project behavior.

Access rules summary: admins bypass task access checks; `task:*:all` grants
all-scope task access; own-department scoped permissions apply to the employee's
own department; workspace/department membership controls scoped read access.
`allow_any_employee` only widens assignment choices and does not widen read
access.

Subtasks are limited to a maximum depth of 1: parent task -> direct subtask only.

Task notifications use polling only. No websockets or server-sent events are
planned; frontend clients poll every NOTIFICATION_POLL_INTERVAL_SECONDS.
"""

# Hierarchy
MAX_SUBTASK_DEPTH: int = 1  # max depth: parent task -> direct subtask only

# Content limits
MAX_DESCRIPTION_BYTES: int = 65_536  # 64 KB
MAX_ATTACHMENT_BYTES: int = 26_214_400  # 25 MB
MAX_ATTACHMENTS_PER_TASK: int = 10

# Notification
NOTIFICATION_POLL_INTERVAL_SECONDS: int = 30  # frontend polls this interval

# Kanban
POSITION_GAP: float = 1000.0  # initial gap between items; halve on conflict
POSITION_MIN: float = 0.0
POSITION_MAX: float = 1_000_000.0

# Versioning (optimistic concurrency)
INITIAL_TASK_VERSION: int = 1

# WIP / aging advisory defaults
WIP_POLICIES: list[str] = ["off", "warn", "enforce"]
AGING_DEFAULT_DAYS: int = 7

# Phase 2 — Agile semantics
TASK_TYPES: list[str] = ["story", "task", "bug", "epic", "spike"]
ESTIMATE_SIZES: list[str] = ["xs", "s", "m", "l", "xl"]
SPRINT_STATUSES: list[str] = ["planned", "active", "completed", "cancelled"]

# Activity verbs for Phase 2 mutations. Kept as module-level constants so
# callers never hard-code the literal strings into TaskActivity.verb.
ACTIVITY_VERB_TASK_TYPE_CHANGED: str = "task_type_changed"
ACTIVITY_VERB_ESTIMATE_CHANGED: str = "estimate_changed"
ACTIVITY_VERB_STORY_POINTS_CHANGED: str = "story_points_changed"
ACTIVITY_VERB_ACCEPTANCE_CRITERIA_CHANGED: str = "acceptance_criteria_changed"
ACTIVITY_VERB_DOR_UPDATED: str = "dor_updated"
ACTIVITY_VERB_DOD_UPDATED: str = "dod_updated"
ACTIVITY_VERB_TASK_BLOCKED: str = "task_blocked"
ACTIVITY_VERB_TASK_UNBLOCKED: str = "task_unblocked"
ACTIVITY_VERB_SPRINT_ASSIGNED: str = "sprint_assigned"
ACTIVITY_VERB_SPRINT_REMOVED: str = "sprint_removed"
ACTIVITY_VERB_SPRINT_ID_CLEARED_ON_PROJECT_MOVE: str = "sprint_id_cleared_on_project_move"
ACTIVITY_VERB_SPRINT_STARTED: str = "sprint_started"
ACTIVITY_VERB_SPRINT_COMPLETED: str = "sprint_completed"

# Stable ASCII-only error codes for Vietnamese UI/API payloads
FEATURE_DISABLED_ERROR_CODE: str = "FEATURE_DISABLED"
WIP_EXCEEDED_ERROR_CODE: str = "WIP_EXCEEDED"
AGING_WARNING_ERROR_CODE: str = "AGING_WARNING"

# Phase 4 — Knowledge integration: link type vocabulary + activity verbs.
KNOWLEDGE_LINK_TYPES: list[str] = ["reference", "solution", "blocker", "related"]
ACTIVITY_VERB_KNOWLEDGE_LINK_ADDED: str = "knowledge_link_added"
ACTIVITY_VERB_KNOWLEDGE_LINK_REMOVED: str = "knowledge_link_removed"

# Default states created per new TaskProject (order matters)
DEFAULT_STATE_NAMES: list[str] = [
    "Backlog",
    "Todo",
    "In Progress",
    "In Review",
    "Done",
    "Cancelled",
]

# State groups for default states
DEFAULT_STATE_GROUPS: list[str] = [
    "backlog",
    "todo",
    "in_progress",
    "review",
    "done",
    "cancelled",
]

# Priority levels (ordered low -> high)
PRIORITY_LEVELS: list[str] = ["none", "low", "medium", "high", "urgent"]

# Scope options for TaskProject parent
TASK_PROJECT_SCOPE_WORKSPACE: str = "workspace"
TASK_PROJECT_SCOPE_DEPARTMENT: str = "department"
