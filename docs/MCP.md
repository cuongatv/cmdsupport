# MCP & Claude Integration

CMD Support exposes a Model Context Protocol (MCP) server at `/mcp`. Employees connect Claude Desktop — or any MCP-compatible client — using a personal token. Claude then has access to the compiled wiki, raw source documents, and AI skills, all filtered to the employee's permission scope.

---

## Connecting Claude Desktop

### Step 1 — Generate an MCP token

In the Admin Portal: **Employees → [employee name] → Generate Token**

The token starts with `ark_` and is shown only once. Copy it before closing.

### Step 2 — Add to Claude Desktop config

Locate the Claude Desktop config file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the CMD Support server:

```json
{
  "mcpServers": {
    "cmd_support": {
      "url": "https://your-cmd-support-server/mcp",
      "headers": {
        "Authorization": "Bearer ark_xxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

For local development:
```json
{
  "mcpServers": {
    "cmd_support": {
      "url": "http://localhost:5055/mcp",
      "headers": {
        "Authorization": "Bearer ark_xxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

### Step 3 — Restart Claude Desktop

CMD Support tools will appear in Claude's tool list. The employee's wiki knowledge is immediately available.

---

## Authentication

Every MCP request is authenticated via bearer token:

```
Authorization: Bearer ark_xxxxxxxxxxxxxxxxxxxx
```

The token is resolved to an employee identity that determines:
- Which knowledge types the employee can access
- Which departments' documents are visible
- Which workspaces they are a member of
- Whether they have write/review permissions

Tokens can be revoked at any time from the Admin Portal.

---

## MCP Tool Reference

Tools are organized in four tiers by permission level.

---

### Tier 1 — Read (all authenticated employees)

#### `search_wiki`
Semantic search across the knowledge wiki. Results are filtered to the employee's permission scope.

```
search_wiki(query: str, top_k: int = 5) → list of pages with similarity scores
```

#### `read_wiki_page`
Read the full markdown content of a specific wiki page.

```
read_wiki_page(slug: str) → page content, title, summary, backlinks, version
```

#### `list_wiki_pages`
Browse wiki pages by type or knowledge category.

```
list_wiki_pages(page_type?: str, knowledge_type_slug?: str, limit: int = 20)
```

#### `read_wiki_index`
Get the full wiki catalog (all pages with slug, type, summary).

```
read_wiki_index() → catalog of all accessible pages
```

#### `list_sources`
Browse uploaded source documents visible to this employee.

```
list_sources(knowledge_type_slug?: str, limit: int = 20)
```

#### `get_source`
Get metadata and processing status for a source document.

```
get_source(source_id: str) → title, type, status, knowledge_type
```

#### `get_source_outline`
Get the table of contents (heading tree) of a source document.

```
get_source_outline(source_id: str) → hierarchical heading structure
```

#### `get_source_pages`
Read raw text from specific pages of a source document. Useful for exact citations.

```
get_source_pages(source_id: str, pages: str) → raw text (e.g. pages="5-7")
```

#### `find_contacts`
Search the internal people directory.

```
find_contacts(query: str) → matching contacts with name, role, contact info
```

#### `list_knowledge_types`
List all knowledge type categories defined in the system.

```
list_knowledge_types() → name, slug, description for each type
```

#### `get_knowledge_type_docs`
List all source documents of a specific knowledge type.

```
get_knowledge_type_docs(knowledge_type_slug: str) → documents in this category
```

---

### Tier 2 — Contribute (workspace contributor+, or `wiki:write:own_dept`)

#### `propose_wiki_edit`
Propose an edit to an existing wiki page. Creates a pending draft that goes through editor review before being applied.

```
propose_wiki_edit(slug: str, content_md: str, note?: str)
→ "Draft submitted. An editor will review it. Draft ID: ..."
```

Use `search_wiki()` or `read_wiki_index()` to find the right slug first.

---

### Tier 3 — Direct Edit (workspace editor+, or `wiki:write:all` for global pages)

#### `edit_wiki_page`
Directly edit a wiki page. The change takes effect immediately — no review step. A revision is created in history.

```
edit_wiki_page(slug: str, content_md: str, change_note?: str)
→ "Page '{slug}' updated to v{version}."
```

Use `propose_wiki_edit()` instead if you only have contributor access.

---

### Tier 4 — Review (workspace editor+, or `wiki:write:all`)

#### `list_pending_drafts`
List pending wiki drafts awaiting your review. Optionally filter by workspace.

```
list_pending_drafts(workspace_id?: str)
→ formatted list with draft_id, page_slug, author, created_at, note
```

#### `review_draft`
Read the full content of a pending draft alongside the current page content for comparison.

```
review_draft(draft_id: str)
→ proposed content + current page content side by side
```

#### `approve_draft`
Approve a pending draft. Optionally provide edited content before approving.

```
approve_draft(draft_id: str, reviewer_note?: str, edited_content_md?: str)
→ "Draft approved. Page updated to v{version}."
```

#### `reject_draft`
Reject a pending draft. `reviewer_note` is required — the contributor needs to know why.

```
reject_draft(draft_id: str, reviewer_note: str)
→ "Draft rejected."
```

---

## Permission scope in MCP

When an employee connects via MCP, their token resolves to a `ResolvedIdentity` that carries:

- `allowed_knowledge_types` — which knowledge type slugs they can access (`null` = unrestricted)
- `allowed_source_ids` — derived from knowledge types + department scope
- `is_admin` — system admin override

All tool responses are filtered against this identity. An employee can only see wiki pages, sources, and skills that match their permission scope. Workspace-scoped resources are additionally restricted to workspace members.

---

## Token management

| Action | Where |
|---|---|
| Generate token | Admin Portal → Employees → [employee] → Generate Token |
| Revoke token | Admin Portal → Employees → [employee] → Revoke Token |
| View active tokens | Admin Portal → Employees → [employee] → Tokens |

A single employee can have multiple active tokens (e.g. Claude Desktop + Claude.ai).

---

## Using CMD Support with Claude.ai (remote MCP)

Claude.ai supports remote MCP servers. Add CMD Support as a remote server with the same URL and token:

```
URL: https://your-cmd-support-server/mcp
Header: Authorization: Bearer ark_xxxxxxxxxxxxxxxxxxxx
```

The same tools and permission scoping apply.

---

## Example conversation

```
Employee: What is our fire safety evacuation procedure?

Claude: [calls search_wiki("fire safety evacuation")]
        [reads wiki page concept/fire-evacuation-procedure]

Based on your organization's SOPs, the fire safety evacuation procedure is...
[synthesized answer from the compiled wiki page]

For the exact wording from the original document, I can check:
[calls get_source_outline(source_id="...")]
[calls get_source_pages(source_id="...", pages="12-14")]
```

---

## Troubleshooting MCP connections

| Issue | Solution |
|---|---|
| Tools don't appear in Claude | Restart Claude Desktop after editing the config |
| "Authentication required" error | Check that `Authorization: Bearer ark_...` header is set correctly |
| "Invalid or inactive token" | Token may have been revoked; generate a new one |
| Tools return empty results | Employee may have no accessible knowledge types — check their role in the portal |
| Connection refused | Ensure the CMD Support API is running and accessible from the client network |
| HTTPS certificate errors | Configure a valid TLS certificate on your CMD Support server |
