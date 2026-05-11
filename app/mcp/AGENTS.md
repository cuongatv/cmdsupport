# app/mcp/ — MCP server (FastMCP)

## OVERVIEW
Exposes the wiki + raw sources + skills to Claude Desktop (and any MCP client) at `/mcp`. Built on `fastmcp`. Mounted into the FastAPI app from `app/main.py` — the MCP lifespan wraps the FastAPI lifespan, so order matters.

## FILES
| File | Role |
|---|---|
| `server.py` | `create_mcp_server()` factory. Sets the system `instructions` shown to Claude on connect. Called once at startup. |
| `tools.py` | **40 KB.** All MCP tool definitions registered via `register_tools(mcp)`. One module on purpose — Claude sees a flat tool list. |
| `resources.py` | MCP "resources" (read-only fixtures + dynamic listings) registered via `register_resources(mcp)`. |

## ADDING A TOOL
1. Add a `@mcp.tool()` function inside `register_tools(mcp)` in `tools.py`.
2. Tool name = function name. **Don't rename existing tools** — clients have hardcoded references.
3. First arg pattern: derive `employee` from the bearer token via `mcp_auth_service.get_employee_from_context(ctx)`. Every tool call must respect that employee's scope.
4. Return JSON-serializable plain dicts/lists. FastMCP doesn't accept SQLAlchemy models.

## CONVENTIONS
- **Auth via bearer token**, not JWT. Tokens are stored in `mcp_tokens` (see `app/database/models.py`) and resolved by `services/mcp_auth_service.py`. Each token is scoped to one employee.
- **Filter every result by employee scope.** The wiki search tool joins on department + workspace membership before returning hits — copy that pattern, don't shortcut it.
- **Cite-friendly output**: wiki results return slugs, source results return source IDs. The `instructions` tell Claude to cite both.
- **Tool descriptions are what Claude reads.** Spend the words; they're the API contract.

## ANTI-PATTERNS
- **Don't return raw SQLAlchemy models** — FastMCP serialization will hit lazy-load and 500.
- **Don't bypass employee-scope filtering** "just for admin" — admin status is enforced upstream by token issuance, not at query time.
- **Don't split `tools.py`** into multiple files unless you also flatten the registration. A multi-file split that still produces one tool list is just indirection.
- **Don't change MCP tool names** without a deprecation window — clients (Claude Desktop configs) hardcode them.
