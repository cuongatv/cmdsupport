# Wiki System

The CMD Support wiki is the primary knowledge surface. Instead of storing raw document chunks, CMD Support compiles documents into structured, interlinked wiki pages — written by an LLM agent, enriched by every new document you add.

---

## How compilation works

When you upload a document, the background worker runs a two-phase process:

### Phase 1 — Pre-analysis

A single fast LLM call reads the first ~30K characters of the document and returns a structural map:
- Document type and primary language
- Key entities, concepts, and themes
- Which existing wiki pages are likely to be updated
- Which new pages should probably be created

This map is injected into the agent's initial context, giving it a head start before the tool-calling loop begins.

### Phase 2 — Agent loop

A tool-calling LLM agent runs in a loop. It has access to:

| Tool | Purpose |
|---|---|
| `read_wiki_index` | See the full catalog of existing pages |
| `read_wiki_page` | Read any existing page in full |
| `search_wiki` | Semantic search across existing pages |
| `read_source_excerpt` | Read any portion of the source document by character offset |
| `create_page` | Create a new wiki page |
| `update_page` | Update an existing page with new content |
| `append_log` | Add an entry to the wiki activity log |
| `finish` | Signal compilation complete |

The agent decides which pages to create, which to update, and how to write the content. Pages cross-reference each other using `[[wikilinks]]`. The same wiki pages are updated as more documents are added — knowledge accumulates in place rather than creating duplicates.

### Page types

| Type | Description |
|---|---|
| `entity` | A named thing: person, company, product, location |
| `concept` | A process, rule, methodology, or framework |
| `topic` | A broad subject area |
| `source` | A page representing the source document itself |

---

## Wiki page structure

Each page is stored with:
- `slug` — URL-safe identifier (e.g. `concept/fire-safety`, `entity/acme-corp`)
- `title` — human-readable name
- `page_type` — entity / concept / topic / source
- `content_md` — full markdown content
- `summary` — one-sentence summary for index and search
- `knowledge_type_slugs[]` — which knowledge types this page belongs to
- `source_ids[]` — which source documents contributed to this page
- `embedding` — vector for semantic search (pgvector)
- `scope_type` + `scope_id` — global or project-scoped
- `version` — current version number
- `orphaned` — true if all contributing sources have been deleted

---

## Version history

Every change to a wiki page creates an immutable revision record:

```
WikiPageRevision
  page_id       → which page
  version       → monotonically increasing integer
  content_md    → full snapshot of the content at this version
  change_type   → agent_compile | editor_edit | draft_approved | rollback
  changed_by_id → which employee (null for agent compilations)
  change_note   → optional description
  draft_id      → linked draft if change_type = draft_approved
```

### Accessing revision history

- **Portal:** Wiki page → History tab → list of all versions
- **API:** `GET /api/wiki/pages/{slug}/revisions`

### Rollback

Admins can restore any previous version:
- **Portal:** History tab → select version → Rollback
- **API:** `POST /api/wiki/pages/{slug}/revisions/{version}/rollback`

Rollback creates a new revision with `change_type=rollback` — the history is preserved, not overwritten.

---

## Editing wiki pages

Two paths depending on your role:

### Direct edit (Editor / Admin)

Editors can edit a page directly — no review step. The change takes effect immediately and a revision is created.

- **Portal:** Open wiki page → Edit button
- **API:** `PUT /api/wiki/pages/{slug}`
- **MCP:** `edit_wiki_page(slug, content_md, change_note)`

Requires: **workspace editor+** for workspace-scoped pages, or **`wiki:write:all`** for global pages.

### Propose a draft (Contributor)

Contributors propose edits that go through editor review before being applied.

- **Portal:** Open wiki page → Propose Edit
- **API:** `POST /api/wiki/pages/{slug}/drafts`
- **MCP:** `propose_wiki_edit(slug, content_md, note)`

Requires: **workspace contributor+** for workspace-scoped pages, or **`wiki:write:own_dept`** for global pages.

---

## Draft workflow

```
Contributor submits draft
    │
    ▼
Draft status: pending
    │
    ├── Editor reviews → Approve
    │       │
    │       └── content_md applied to page
    │           WikiPageRevision(change_type=draft_approved) created
    │           Draft status → approved
    │
    └── Editor reviews → Reject (reviewer_note required)
            │
            └── Draft status → rejected
                Contributor can see the rejection reason
```

Multiple drafts can be pending for the same page at the same time. Editors resolve them one by one — approving a draft applies its content; later drafts may need to be reviewed again if their base was outdated.

### Editor review actions

**Via portal:** Wiki Drafts queue → select draft → compare side-by-side → Approve or Reject.

**Via API:**
- `GET /api/wiki/drafts` — list pending drafts (filtered to your scope)
- `GET /api/wiki/pages/{slug}/drafts` — drafts for a specific page
- `GET /api/wiki/drafts/{id}` — full draft with current page content
- `POST /api/wiki/drafts/{id}/approve` — approve (optionally with edited content)
- `POST /api/wiki/drafts/{id}/reject` — reject (reviewer_note required)

**Via MCP (for Claude Desktop editors):**
- `list_pending_drafts(workspace_id?)` — see pending drafts
- `review_draft(draft_id)` — read draft vs current content
- `approve_draft(draft_id, reviewer_note?, edited_content_md?)`
- `reject_draft(draft_id, reviewer_note)`

---

## Scope: Global vs. Workspace

Wiki pages are either global or workspace-scoped:

**Global pages** — visible to all employees who have `wiki:read` permission.
Compiled from global sources (documents not assigned to any specific workspace).

**Workspace-scoped pages** — visible only to workspace members.
Compiled from workspace-owned sources. Accessible through the workspace wiki browser.

When a source is uploaded directly into a workspace (via the workspace Sources tab), its compiled wiki pages are automatically scoped to that workspace.

---

## Orphaned pages

When all source documents contributing to a wiki page are deleted, the page is marked `orphaned = true`. It is NOT automatically deleted — editors can review orphaned pages and decide whether to keep, update, or remove them.

- **API:** `GET /api/wiki/orphaned` (admin only)

---

## Knowledge graph

Wiki pages are linked via `[[wikilinks]]` in their content. CMD Support extracts these links into a `wiki_links` table, enabling:

- **Backlinks** — which pages link to this one
- **Outlinks** — which pages this one links to
- **Graph visualization** — interactive node/edge graph in the portal

The full graph is available at `/wiki/graph`. Each workspace also has a scoped graph at `GET /api/projects/{id}/wiki/graph`.

---

## Wiki index and log

Two reserved pages are maintained automatically:

- `_index` — a catalog of all wiki pages, updated after each compilation
- `_log` — a chronological log of ingestion and compilation events

These are visible in the wiki browser and accessible via:
- `GET /api/wiki/index`
- `GET /api/wiki/log`
