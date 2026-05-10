# AI Skills

AI Skills are versioned agent packages that employees can access through Claude via MCP. Upload a skill package, assign it to departments or workspaces, and it becomes available in Claude's tool context for employees with the right permissions. Skills are managed through CMD Support's admin portal.

---

## What is a Skill?

A Skill is a packaged capability — a custom agent, a specialized prompt, or a tool bundle — that your organization develops and distributes through CMD Support. Think of it as an internal app store for AI capabilities.

Examples:
- A **document generator** that fills in report templates from structured input
- A **contract reviewer** trained on your organization's legal standards
- A **customer profile builder** that pulls from your CRM data format
- A **translation agent** calibrated to your industry's terminology

Skills are uploaded as packages, versioned, and scoped to specific departments or workspaces. When a scoped employee connects via MCP, their permitted skills are available to Claude automatically.

---

## Uploading a Skill

**Admin Portal → Skills → Upload Skill**

Required:
- **Name** — human-readable skill name
- **Slug** — URL-safe identifier (e.g. `document-generator`)
- **Package file** — the skill package (format depends on your implementation)
- **Description** — what this skill does

Optional:
- **Department scope** — restrict to specific departments (no departments = global, visible to all)
- **Knowledge type** — associate the skill with a knowledge category

The background skill worker processes the uploaded package. Status progresses: `pending` → `processing` → `active`.

---

## Versioning

Every skill has a version history:
- `current_version` — active version number (integer)
- Each upload or update creates a new `SkillVersion` record with a version hash and storage path
- Changelog notes are optional but recommended

To release a new version:
**Admin Portal → Skills → [skill name] → Upload New Version**

Old versions are preserved. Rolling back to a previous version is available from the version history panel.

---

## Access control

Skills follow the same dual-realm permission model as documents and wiki:

**Global realm (department-based):**
- No departments assigned → **Global skill** — visible to all employees with `skill:read:own_dept` or higher
- Departments assigned → visible only to employees whose department matches

**Workspace realm:**
- Skills can be scoped to a specific workspace (`scope_type = project`)
- Only workspace members can access workspace-scoped skills

**Permission levels:**
| Permission | What it grants |
|---|---|
| `skill:read:own_dept` | View and use skills in your department + global skills |
| `skill:read:all` | View and use all skills across all departments |
| `skill:create:own_dept` | Upload skills to your department |
| `skill:create:all` | Upload skills to any department |
| `skill:edit:own_dept` | Edit skill metadata in your department |
| `skill:edit:all` | Edit any skill |
| `skill:delete:own_dept` | Delete skills in your department |
| `skill:delete:all` | Delete any skill |

---

## Skill visibility in MCP

When an employee connects Claude via MCP:
1. CMD Support resolves their identity and permission scope
2. Skills accessible to this employee (based on department + workspace membership) are included in the MCP context
3. Claude can reference and use these skills in conversation

Skills that are `processing`, `deprecated`, or `archived` are not surfaced in MCP.

---

## Skill lifecycle

```
Upload package
    │
    ▼
status: pending
    │
    ▼ (skill worker processes)
status: processing
    │
    ▼
status: active  ──→  available in MCP for scoped employees
    │
    ├── Update version  ──→  new SkillVersion, current_version bumped
    │
    ├── Deprecate  ──→  status: deprecated (no longer surfaced in MCP)
    │
    └── Archive  ──→  status: archived (hidden from lists)
```

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/skills` | List skills (filtered to user's scope) |
| `POST` | `/api/skills/upload` | Upload a new skill package |
| `GET` | `/api/skills/{id}` | Get skill details |
| `PATCH` | `/api/skills/{id}` | Update skill metadata |
| `DELETE` | `/api/skills` | Delete skills (bulk) |
| `GET` | `/api/skills/{id}/versions` | List version history |
| `POST` | `/api/skills/bulk-visibility` | Set department/scope for multiple skills |
