# Access Control

CMD Support has a dual-realm permission system:

1. **Global realm** — department-based RBAC for organization-wide resources (documents, wiki, skills)
2. **Workspace realm** — membership-based roles for project-scoped resources

These two realms are independent. Global permissions do not grant workspace access, and workspace membership does not grant access to global resources by itself.

---

## Global Realm — Permissions

### Permission format

```
{resource}:{action}:{scope}

scope options:
  own_dept  →  your department + global (unscoped) resources
  all       →  all resources regardless of department
```

### Full permission list

**Documents**
| Permission | Description |
|---|---|
| `doc:read:own_dept` | View documents in your department and global documents |
| `doc:read:all` | View all documents across all departments |
| `doc:create:own_dept` | Upload documents to your department |
| `doc:create:all` | Upload documents to any department |
| `doc:edit:own_dept` | Edit document metadata in your department |
| `doc:edit:all` | Edit any document |
| `doc:delete:own_dept` | Delete documents in your department |
| `doc:delete:all` | Delete any document |

**Wiki**
| Permission | Description |
|---|---|
| `wiki:read:own_dept` | Read global wiki + wiki pages scoped to your dept |
| `wiki:read:all` | Read all wiki pages |
| `wiki:write:own_dept` | Propose wiki drafts for global pages |
| `wiki:write:all` | Direct edit any wiki page + approve/reject drafts on global pages |
| `wiki:delete:own_dept` | Delete wiki pages in your dept scope |
| `wiki:delete:all` | Delete any wiki page |

**AI Skills**
| Permission | Description |
|---|---|
| `skill:read:own_dept` | Use skills in your department + global skills |
| `skill:read:all` | Use all skills |
| `skill:create:own_dept` | Upload skills to your department |
| `skill:create:all` | Upload skills anywhere |
| `skill:edit:own_dept` | Edit skill metadata in your department |
| `skill:edit:all` | Edit any skill |
| `skill:delete:own_dept` | Delete skills in your department |
| `skill:delete:all` | Delete any skill |

**Organization (admin operations)**
| Permission | Description |
|---|---|
| `org:departments:read` | View departments |
| `org:departments:manage` | Create/edit/delete departments |
| `org:employees:read` | View employee directory |
| `org:employees:manage` | Create/edit/deactivate employees |
| `org:roles:read` | View roles and their permissions |
| `org:roles:manage` | Create/edit/delete roles |
| `org:settings:read` | View system settings |
| `org:settings:manage` | Modify system settings (AI providers, keys) |
| `org:audit:read` | View audit log |

**Workspaces**
| Permission | Description |
|---|---|
| `workspace:view:all` | View all workspaces without being a member |

---

### Roles

A **Role** is a named collection of permissions assigned to employees. Roles are created and managed in **Admin Portal → Roles**.

**Built-in role presets:**

| Preset | Included permissions |
|---|---|
| **Viewer** | `doc:read:own_dept`, `wiki:read:own_dept`, `skill:read:own_dept`, `org:departments:read` |
| **Contributor** | Viewer + `doc:create:own_dept`, `wiki:write:own_dept`, `skill:create:own_dept` |
| **Department Admin** | Contributor + edit/delete for own dept (docs, wiki, skills) |
| **Knowledge Admin** | All `:all` permissions for docs, wiki, and skills |

**Default employee permissions** (when no custom role is assigned):
`doc:read:own_dept`, `doc:create:own_dept`, `wiki:read:own_dept`, `wiki:write:own_dept`, `skill:read:own_dept`

---

### System Admin

The `admin` role (set on the Employee model) is a system-level override:
- Bypasses all permission checks
- Has workspace admin role in every workspace automatically
- Can create and delete workspaces
- Can view and manage all resources regardless of department

---

## Workspace Realm — Membership Roles

Each workspace (project) has its own member list. Membership roles are separate from global permissions.

### Roles

| Role | Level | What they can do |
|---|---|---|
| **Viewer** | 0 | Read wiki pages, sources, and member list of the workspace |
| **Contributor** | 1 | + Propose wiki drafts for workspace pages |
| **Editor** | 2 | + Direct edit wiki pages · Approve/reject drafts · Add/remove sources · Upload files to workspace |
| **Admin** | 3 | + Add/remove members · Change member roles · Rename/archive the workspace |

Roles are hierarchical — Editor can do everything Contributor can, and so on.

### Guards

- **Last admin protection** — the last workspace admin cannot be removed or demoted. Assign another admin first.
- **Workspace deletion** — only system admins can delete workspaces, regardless of workspace role.
- **Workspace creation** — only system admins can create workspaces.

---

## How scope resolution works

### Global documents

```
User has doc:read:own_dept?
  → Source has no departments (Global doc)?   → Accessible ✓
  → Source's departments include user's dept? → Accessible ✓
  → Otherwise                                 → Blocked ✗

User has doc:read:all?
  → Accessible regardless of source departments ✓
```

### Workspace resources

```
User is system admin?            → Full access ✓
User is workspace member?        → Access (filtered by workspace role)
Otherwise                        → 403 Forbidden
```

### Wiki pages

```
Global wiki page:
  → User has wiki:read:own_dept or wiki:read:all → Accessible ✓
  → Otherwise → Blocked ✗

Workspace-scoped wiki page:
  → User has wiki:read:own_dept AND is workspace member → Accessible ✓
  → User has wiki:read:all                             → Accessible ✓
  → Otherwise → Blocked ✗
```

### Wiki write permissions (global pages)

| Action | Required permission |
|---|---|
| Propose a draft | `wiki:write:own_dept` or `wiki:write:all` |
| Direct edit | `wiki:write:all` |
| Approve / reject draft | `wiki:write:all` |

For **workspace-scoped** pages, global permissions are not used — workspace roles apply:

| Action | Required workspace role |
|---|---|
| Propose a draft | Contributor+ |
| Direct edit | Editor+ |
| Approve / reject draft | Editor+ |

---

## Setting up access control (step by step)

### 1. Create departments

**Admin Portal → Departments → New Department**

Departments define the scope boundary for `own_dept` permissions. Every employee belongs to one department.

### 2. Create roles

**Admin Portal → Roles → New Role**

Select the permissions this role should grant. You can start from a built-in preset and customize.

### 3. Create employees

**Admin Portal → Employees → New Employee**

Assign each employee to a department and a role.

### 4. Assign knowledge types to sources

When uploading documents, assign them a knowledge type. This determines which employees can see them via MCP (based on their MCP token's `allowed_knowledge_types`).

### 5. Create workspaces and add members

**Admin Portal → Workspaces → New Workspace**

Add employees as workspace members and assign their workspace role (Viewer, Contributor, Editor, or Admin).

---

## MCP token scoping

When an MCP token is generated for an employee, it captures their current permission scope:
- Which knowledge types they can access
- Their department

This scope is re-evaluated on each request based on the live state of their role and department assignments. Revoking a token or changing an employee's role takes effect immediately.
