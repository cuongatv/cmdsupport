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
