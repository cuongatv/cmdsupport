"""
Permission constants for Arkon's dual-realm RBAC system.

Format: {resource}:{action}:{scope}
  - scope = "own_dept" → only own department + global resources
  - scope = "all" → all resources

Organization permissions have no scope (they are global admin actions).
Workspace permissions are separate (workspace:view:all for admin override).

All permission strings are defined here as the single source of truth.
Used by: require_permission() in auth_service, Role CRUD, and the frontend UI.
"""

# ---------------------------------------------------------------------------
# All permissions (ordered for UI display)
# ---------------------------------------------------------------------------

ALL_PERMISSIONS: list[str] = [
    # Documents
    "doc:read:own_dept", "doc:read:all",
    "doc:create:own_dept", "doc:create:all",
    "doc:edit:own_dept", "doc:edit:all",
    "doc:delete:own_dept", "doc:delete:all",

    # Wiki
    "wiki:read:own_dept", "wiki:read:all",
    "wiki:write:own_dept", "wiki:write:all",
    "wiki:delete:own_dept", "wiki:delete:all",

    # AI Skills
    "skill:read:own_dept", "skill:read:all",
    "skill:create:own_dept", "skill:create:all",
    "skill:edit:own_dept", "skill:edit:all",
    "skill:delete:own_dept", "skill:delete:all",

    # Tasks
    "task:read:own_dept", "task:read:all",
    "task:create:own_dept", "task:create:all",
    "task:edit:own_dept", "task:edit:all",
    "task:delete:own_dept", "task:delete:all",
    "task_project:manage:own_dept", "task_project:manage:all",

    # CMD Support
    "cmd:advice:create",
    "cmd:advice:read:own",
    "cmd:advice:read:all",

    # Organization
    "org:departments:read", "org:departments:manage",
    "org:employees:read", "org:employees:manage",
    "org:roles:read", "org:roles:manage",
    "org:settings:read", "org:settings:manage",
    "org:audit:read",

    # Workspaces
    "workspace:view:all",
]


# ---------------------------------------------------------------------------
# Default permissions for system role "employee" (no custom role assigned)
# ---------------------------------------------------------------------------

EMPLOYEE_DEFAULT_PERMISSIONS: list[str] = [
    "doc:read:own_dept",
    "doc:create:own_dept",
    "wiki:read:own_dept",
    "wiki:write:own_dept",
    "skill:read:own_dept",
    "task:read:own_dept",
    "task:create:own_dept",
]

# ---------------------------------------------------------------------------
# Permission groups (for UI rendering)
# ---------------------------------------------------------------------------

PERMISSION_GROUPS: dict[str, list[str]] = {
    "Documents": [
        "doc:read:own_dept", "doc:read:all",
        "doc:create:own_dept", "doc:create:all",
        "doc:edit:own_dept", "doc:edit:all",
        "doc:delete:own_dept", "doc:delete:all",
    ],
    "Wiki": [
        "wiki:read:own_dept", "wiki:read:all",
        "wiki:write:own_dept", "wiki:write:all",
        "wiki:delete:own_dept", "wiki:delete:all",
    ],
    "AI Skills": [
        "skill:read:own_dept", "skill:read:all",
        "skill:create:own_dept", "skill:create:all",
        "skill:edit:own_dept", "skill:edit:all",
        "skill:delete:own_dept", "skill:delete:all",
    ],
    "Tasks": [
        "task:read:own_dept", "task:read:all",
        "task:create:own_dept", "task:create:all",
        "task:edit:own_dept", "task:edit:all",
        "task:delete:own_dept", "task:delete:all",
        "task_project:manage:own_dept", "task_project:manage:all",
    ],
    "CMD Support": [
        "cmd:advice:create",
        "cmd:advice:read:own",
        "cmd:advice:read:all",
    ],
    "Organization": [
        "org:departments:read", "org:departments:manage",
        "org:employees:read", "org:employees:manage",
        "org:roles:read", "org:roles:manage",
        "org:settings:read", "org:settings:manage",
        "org:audit:read",
    ],
    "Workspaces": [
        "workspace:view:all",
    ],
}


PERMISSION_LABELS: dict[str, str] = {
    # Documents
    "doc:read:own_dept":      "View documents (own department + global)",
    "doc:read:all":           "View all documents (all departments)",
    "doc:create:own_dept":    "Upload documents (own department)",
    "doc:create:all":         "Upload documents (any department)",
    "doc:edit:own_dept":      "Edit documents (own department)",
    "doc:edit:all":           "Edit all documents",
    "doc:delete:own_dept":    "Delete documents (own department)",
    "doc:delete:all":         "Delete all documents",

    # Wiki
    "wiki:read:own_dept":     "View wiki pages (own department + global)",
    "wiki:read:all":          "View all wiki pages",
    "wiki:write:own_dept":    "Create/edit wiki pages (own department)",
    "wiki:write:all":         "Create/edit all wiki pages",
    "wiki:delete:own_dept":   "Delete wiki pages (own department)",
    "wiki:delete:all":        "Delete all wiki pages",

    # AI Skills
    "skill:read:own_dept":    "View AI skills (own department + global)",
    "skill:read:all":         "View all AI skills",
    "skill:create:own_dept":  "Upload AI skills (own department)",
    "skill:create:all":       "Upload AI skills (any department)",
    "skill:edit:own_dept":    "Edit AI skills (own department)",
    "skill:edit:all":         "Edit all AI skills",
    "skill:delete:own_dept":  "Delete AI skills (own department)",
    "skill:delete:all":       "Delete all AI skills",

    # Tasks
    "task:read:own_dept":     "View tasks (own department + global)",
    "task:read:all":          "View all tasks",
    "task:create:own_dept":   "Create tasks (own department)",
    "task:create:all":        "Create tasks (all departments)",
    "task:edit:own_dept":     "Edit tasks (own department)",
    "task:edit:all":          "Edit all tasks",
    "task:delete:own_dept":   "Delete tasks (own department)",
    "task:delete:all":        "Delete all tasks",
    "task_project:manage:own_dept": "Manage task projects (own department)",
    "task_project:manage:all":      "Manage all task projects",

    # CMD Support
    "cmd:advice:create":      "Tạo phiên tư vấn KHDN",
    "cmd:advice:read:own":    "Xem phiên tư vấn của mình",
    "cmd:advice:read:all":    "Xem tất cả phiên tư vấn",

    # Organization
    "org:departments:read":   "View departments",
    "org:departments:manage": "Manage departments (create/edit/delete)",
    "org:employees:read":     "View employees",
    "org:employees:manage":   "Manage employees (create/edit/deactivate)",
    "org:roles:read":         "View roles & positions",
    "org:roles:manage":       "Manage roles (create/edit/delete)",
    "org:settings:read":      "View system settings",
    "org:settings:manage":    "Manage system settings",
    "org:audit:read":         "View audit log",

    # Workspaces
    "workspace:view:all":     "View all workspaces (admin override)",
}


# Detailed descriptions for admin tooltips
PERMISSION_DESCRIPTIONS: dict[str, str] = {
    # Documents
    "doc:read:own_dept":      "View documents assigned to your department and Global documents (not tied to any department).",
    "doc:read:all":           "View all documents across every department. Typically for admins or librarians.",
    "doc:create:own_dept":    "Upload new documents and assign them to your own department only.",
    "doc:create:all":         "Upload new documents and assign them to any department in the system.",
    "doc:edit:own_dept":      "Edit document metadata (title, type, departments) for documents in your department.",
    "doc:edit:all":           "Edit metadata for any document in the system regardless of department.",
    "doc:delete:own_dept":    "Delete documents belonging to your department. This action cannot be undone.",
    "doc:delete:all":         "Delete any document in the system. Dangerous — only grant to trusted admins.",

    # Wiki
    "wiki:read:own_dept":     "Read wiki pages scoped to your department and Global wiki pages.",
    "wiki:read:all":          "Read all wiki pages across every department.",
    "wiki:write:own_dept":    "Create and edit wiki pages within your department's scope.",
    "wiki:write:all":         "Create and edit any wiki page in the system.",
    "wiki:delete:own_dept":   "Delete wiki pages belonging to your department.",
    "wiki:delete:all":        "Delete any wiki page. Dangerous — only grant to trusted admins.",

    # AI Skills
    "skill:read:own_dept":    "View AI skills scoped to your department and Global skills.",
    "skill:read:all":         "View all AI skills across every department.",
    "skill:create:own_dept":  "Upload AI skills to your department.",
    "skill:create:all":       "Upload AI skills to any department.",
    "skill:edit:own_dept":    "Edit AI skills metadata for your department.",
    "skill:edit:all":         "Edit any AI skill in the system.",
    "skill:delete:own_dept":  "Delete AI skills belonging to your department.",
    "skill:delete:all":       "Delete any AI skill. Dangerous.",

    # Tasks
    "task:read:own_dept":     "View tasks assigned to your department and global tasks.",
    "task:read:all":          "View all tasks across every department.",
    "task:create:own_dept":   "Create tasks for your department.",
    "task:create:all":        "Create tasks for any department.",
    "task:edit:own_dept":     "Edit tasks in your department.",
    "task:edit:all":          "Edit any task in the system.",
    "task:delete:own_dept":   "Delete tasks in your department.",
    "task:delete:all":        "Delete any task. Dangerous.",
    "task_project:manage:own_dept": "Manage task projects in your department.",
    "task_project:manage:all":      "Manage any task project in the system.",

    # CMD Support
    "cmd:advice:create":         "Tạo phiên tư vấn sản phẩm dịch vụ cho khách hàng doanh nghiệp, sử dụng AI phân tích từ wiki nội bộ.",
    "cmd:advice:read:own":       "Xem lại các phiên tư vấn KHDN mà bạn đã tạo.",
    "cmd:advice:read:all":       "Xem tất cả phiên tư vấn KHDN trong hệ thống, bao gồm của nhân viên khác.",

    # Organization
    "org:departments:read":      "View the list of departments and their details. Required for most admin views.",
    "org:departments:manage": "Create, edit, and delete departments. Changes affect document access scopes.",
    "org:employees:read":     "View the employee directory including names, emails, and departments.",
    "org:employees:manage":   "Create accounts, edit profiles, and deactivate employees. Includes role assignment.",
    "org:roles:read":         "View the list of roles and their associated permissions.",
    "org:roles:manage":       "Create, edit, and delete roles and modify their permissions. Highly sensitive — controls who can do what.",
    "org:settings:read":      "View system configuration (AI providers, masked API keys). Read-only access.",
    "org:settings:manage":    "Modify system settings such as AI provider, model, and API keys. Admin-level privilege.",
    "org:audit:read":         "View the audit log tracking all system activities.",

    # Workspaces
    "workspace:view:all":     "View all workspaces even without being a member. By default, only admins have this.",
}


# ---------------------------------------------------------------------------
# Preset role templates (for seed data / quick setup)
# ---------------------------------------------------------------------------

ROLE_PRESETS: dict[str, dict[str, object]] = {
    "Viewer": {
        "description": "Basic read-only access to own department documents and wiki",
        "permissions": ["doc:read:own_dept", "wiki:read:own_dept", "skill:read:own_dept", "org:departments:read"],
        "is_system": True,
    },
    "Contributor": {
        "description": "Can read and create documents/wiki in own department",
        "permissions": [
            "doc:read:own_dept", "doc:create:own_dept",
            "wiki:read:own_dept", "wiki:write:own_dept",
            "skill:read:own_dept", "skill:create:own_dept",
            "cmd:advice:create", "cmd:advice:read:own",
            "org:departments:read",
        ],
        "is_system": True,
    },
    "Department Admin": {
        "description": "Full access to own department's documents and wiki",
        "permissions": [
            "doc:read:own_dept", "doc:create:own_dept",
            "doc:edit:own_dept", "doc:delete:own_dept",
            "wiki:read:own_dept", "wiki:write:own_dept", "wiki:delete:own_dept",
            "skill:read:own_dept", "skill:create:own_dept", "skill:edit:own_dept", "skill:delete:own_dept",
            "cmd:advice:create", "cmd:advice:read:own",
            "org:departments:read",
        ],
        "is_system": True,
    },
    "Knowledge Admin": {
        "description": "Full access to all documents and wiki across all departments",
        "permissions": [
            "doc:read:all", "doc:create:all", "doc:edit:all", "doc:delete:all",
            "wiki:read:all", "wiki:write:all", "wiki:delete:all",
            "skill:read:all", "skill:create:all", "skill:edit:all", "skill:delete:all",
            "cmd:advice:create", "cmd:advice:read:all",
        ],
        "is_system": True,
    },
}


# ---------------------------------------------------------------------------
# Legacy migration map (old permission → new scoped permissions)
# ---------------------------------------------------------------------------

LEGACY_PERMISSION_MAP: dict[str, list[str]] = {
    "documents.read":      ["doc:read:own_dept"],
    "documents.create":    ["doc:create:own_dept"],
    "documents.edit":      ["doc:edit:own_dept"],
    "documents.delete":    ["doc:delete:own_dept"],
    "kb.read":             ["wiki:read:own_dept"],
    "kb.create":           ["wiki:write:own_dept"],
    "kb.edit":             ["wiki:write:own_dept"],
    "kb.delete":           ["wiki:delete:own_dept"],
    "departments.read":    ["org:departments:read"],
    "departments.create":  ["org:departments:manage"],
    "departments.edit":    ["org:departments:manage"],
    "departments.delete":  ["org:departments:manage"],
    "employees.read":      ["org:employees:read"],
    "employees.create":    ["org:employees:manage"],
    "employees.edit":      ["org:employees:manage"],
    "employees.delete":    ["org:employees:manage"],
    "roles.read":          ["org:roles:read"],
    "roles.create":        ["org:roles:manage"],
    "roles.edit":          ["org:roles:manage"],
    "roles.delete":        ["org:roles:manage"],
    "settings.read":       ["org:settings:read"],
    "settings.edit":       ["org:settings:manage"],
    "workspaces.read":     ["workspace:view:all"],
    "workspaces.create":   [],  # Workspace creation is admin-only now
    "workspaces.edit":     [],
    "workspaces.delete":   [],
    "scopes.read":         [],  # Removed
    "scopes.manage":       [],  # Removed
    "audit.read":          ["org:audit:read"],
    # AI Skills (legacy mapping)
    "skills.read":         ["skill:read:own_dept"],
    "skills.create":       ["skill:create:own_dept"],
    "skills.edit":         ["skill:edit:own_dept"],
    "skills.delete":       ["skill:delete:own_dept"],
}
