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

---

## Phân loại Wiki theo BIDV KHDN (Wiki Taxonomy)

### Loại trang Wiki (Page types)

`page_type` values are technical identifiers stored in the database. They're stable and not localized:

| page_type | Vietnamese label |
|---|---|
| `entity` | Thực thể (người, công ty, địa điểm) |
| `concept` | Khái niệm / quy trình / phương pháp |
| `topic` | Chủ đề tổng quát |
| `source` | Trang đại diện tài liệu nguồn |
| `index` | Danh mục wiki (hệ thống tạo tự động) |
| `log` | Nhật ký biên soạn (hệ thống tạo tự động) |

Display labels in the portal UI are presentation-only; the `page_type` value in the database never changes.

### Taxonomy nghiệp vụ (KHDN taxonomy)

The BIDV KHDN taxonomy has two tiers seeded by migration `037`. Source of truth: `alembic/versions/037_seed_wiki_taxonomy.py`.

**Tier 1 — Đối tượng nghiệp vụ** (`business_object.*`):

| Slug | Vietnamese label |
|---|---|
| `business_object.product_service` | Sản phẩm & dịch vụ |
| `business_object.target_customer` | Khách hàng mục tiêu / phân khúc |
| `business_object.non_credit_development_tool` | Công cụ phát triển khách hàng phi tín dụng |
| `business_object.credit_development_tool` | Công cụ phát triển khách hàng tín dụng |
| `business_object.campaign_program` | Chiến dịch / chương trình thúc đẩy |
| `business_object.policy_mechanism` | Cơ chế / chính sách |
| `business_object.eligibility_condition` | Điều kiện / tiêu chí áp dụng |
| `business_object.process_form` | Quy trình / hồ sơ / biểu mẫu |
| `business_object.risk_compliance` | Rủi ro / tuân thủ |
| `business_object.industry_segment` | Ngành nghề / lĩnh vực kinh doanh |
| `business_object.region_channel` | Địa bàn / kênh phân phối |
| `business_object.other` | Đối tượng nghiệp vụ khác |

**Tier 2 — Kiến thức bổ trợ** (`supporting_knowledge.*`):

| Slug | Vietnamese label |
|---|---|
| `supporting_knowledge.general_context` | Bối cảnh / thông tin nền |
| `supporting_knowledge.term_explanation` | Giải thích thuật ngữ |
| `supporting_knowledge.operational_guidance` | Hướng dẫn vận hành / hướng dẫn đọc tài liệu |
| `supporting_knowledge.source_background` | Thông tin nguồn / xuất xứ tài liệu |
| `supporting_knowledge.other` | Kiến thức bổ trợ khác |

When the classifier cannot confidently assign a slug, it falls back to `supporting_knowledge.other`.

### Phân loại tại bước xử lý tài liệu

The taxonomy classifier runs automatically at two points:

1. **Legacy compile** — during the wiki agent compilation pipeline, each newly created or updated page is classified before the agent loop finishes.
2. **MRP commit** — when a Multi-Round Processing job commits page changes.

Four fields are persisted on `wiki_pages` after each classification:

| Column | Description |
|---|---|
| `taxonomy_confidence` | Float 0.0–1.0 from the LLM classifier |
| `taxonomy_rationale` | Short explanation (no body text quoted) |
| `taxonomy_needs_review` | True when confidence < 0.80 or slug is the fallback |
| `taxonomy_classifier_version` | String version tag, currently `taxonomy-v1` |

Pages where `taxonomy_needs_review = true` should be reviewed in the Admin Portal before relying on their classification for search filtering or reporting.

### Phân loại lại Wiki sẵn có

Operators with `wiki:write:all` can re-run classification on existing pages without touching page content.

**Step 1 — Preview (non-mutating):**
```
POST /api/wiki/reclassify/preview
```
Accepts optional filters (`source_id`, `page_ids`, `scope_type`, `scope_id`, `limit`). Returns a diff of proposed taxonomy changes. No pages are modified.

**Step 2 — Apply:**
```
POST /api/wiki/reclassify/apply
```
Pass the `preview` dict returned by the preview endpoint. The service re-validates each page by ID before writing.

Key safety rules for apply:
- Pages with `taxonomy_needs_review = true` are skipped unless `force_rule_linked_tier_change = true` is included in the request body.
- Pages linked to consulting rules (tier changes) are also skipped without that flag.
- `wiki_page_id`, `source_ids`, and consulting rule links are all preserved; only taxonomy columns are updated.
- Each applied change creates a standard `WikiPageRevision` record and an audit log entry.

### Không dịch nội dung Wiki

**Guardrail:** taxonomy labels (Vietnamese display names) are localized, but Wiki page bodies and source document content are **không dịch** (not translated). The wiki agent prompts explicitly forbid translating body text. A page compiled from a Vietnamese document stays in Vietnamese; an English source stays in English.

Operators should not edit wiki page content to translate it into another language. If translated content is found, revert to the previous revision using the History tab or the rollback API.
