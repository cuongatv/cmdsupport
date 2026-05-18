
## [2026-05-18] Task 7 admin dashboard router tests
- Created `tests/api/test_admin_dashboard_router.py` with reusable async fixtures inside the file (no new conftest), seeding admin/scoped/no-access employees, 2 task projects, TaskState rows, and active/blocked/completed tasks.
- `auth_headers_factory` mints JWTs with `create_access_token`, so the tests exercise the real auth dependency path without hardcoded tokens.
- `FEATURE_AGILE_PHASE_5` is patched with `monkeypatch` per test, matching the router contract: off returns HTTP 200 with disabled zero-KPI payload; on hits the aggregation service.
- Admin/scoped RBAC coverage is easiest to assert with project_id filters because the service's accessible-project count changes by visible scope; keep that pattern if the route is expanded later.
- Evidence/test execution on the Docker API container required syncing source files into the container because the running image did not have the workspace bind-mounted.


## [2026-05-18] Task 8 â€” AgileKpiStrip component
- Placed at rontend/src/components/admin/dashboard/AgileKpiStrip.tsx to colocate with AgileDashboardShell.tsx and ClassicDashboardView.tsx â€” matches the existing admin dashboard pattern (rather than adding a new dashboard/ folder under components/).
- Props are data: AdminDashboardFlowSummaryResponse | null and loading: boolean. Null data is treated the same as loading=true so the shell can mount it unwired (T14 will plumb real data) without flashing an empty card.
- Render order is: skeleton (loading || data===null) -> disabled (!feature_enabled) -> empty (scoped_project_count === 0) -> 6 KPI cards. Each terminal state owns a unique data-testid so Playwright selectors stay simple.
- KPI labels are Vietnamese; throughput is HoÃ n thÃ nh (never "Velocity") per the project decision logged in earlier waves.
- Approximation badge rides inside the cycle/lead time cards (not as a sibling) so it stays visible on narrow viewports where the 6-card grid collapses to 1-2 columns. The 	itle attribute carries the tooltip copy.
- Drill-down links (locked -> /admin/tasks?blocked=true, ging -> /admin/tasks?aging=true) use 
ext/link; other cards render plain <div> to avoid misleading hover affordances.
- Tailwind 4 tokens used: g-card, order-border, g-muted/50, 	ext-primary, g-secondary / 	ext-secondary-foreground. Confirmed --secondary maps to #E6F3F2 (BIDV primary tint) in globals.css, so the badge stays subtle and on-brand.
- Skeleton uses nimate-pulse + g-muted/50 per the task spec.
- Shell update: removed the kpi placeholder entry from PLACEHOLDER_SECTIONS and rendered <AgileKpiStrip data={null} loading={false} /> above the placeholder grid (full-width 6-card strip > 2-col grid cell).
- Verification: 
px tsc --noEmit -> exit 0; 
pm run lint -> exit 0 (84 pre-existing warnings, none in touched files). Evidence: .sisyphus/evidence/task-8-tsc.txt, .sisyphus/evidence/task-8-lint.txt.


## [2026-05-18] Task 9 - AgileCfd component (Cumulative Flow Diagram)
- Placed at frontend/src/components/admin/dashboard/AgileCfd.tsx alongside AgileKpiStrip.tsx and AgileDashboardShell.tsx - consistent with the T8 pattern (no new dashboard/ subfolder needed for two components).
- Props mirror AgileKpiStrip: { data: AdminDashboardFlowSummaryResponse | null; loading: boolean }. data===null is treated as loading so the shell can mount with data={null} until T14 wires getAdminDashboardFlowSummary.
- CfdDataPoint shape in task-types.ts is { snapshot_date, state_counts: Record<string, number>, blocked_count } - NOT a flat record. The task description hint was misleading on this; always read task-types.ts directly. blocked_count is unused by the CFD (kept for kpi/blocked panels).
- buildChartRows() flattens cfd_series into [{ date, [group]: count, ... }] rows that Recharts AreaChart consumes. Group ordering: preferred (todo -> in_progress -> done -> cancelled) first, then any custom project groups appended sorted alphabetically. Stable ordering prevents stack reshuffling between renders.
- Render order: skeleton (loading || data===null) -> disabled (!feature_enabled, message "Tinh nang chua duoc kich hoat") -> empty (cfd_series.length < 2, message "Chua du du lieu de ve bieu do. Can it nhat 2 ngay du lieu.") -> chart. Each terminal state has a distinct data-testid (chart-cfd-skeleton, chart-cfd-disabled, chart-cfd-empty, chart-cfd-as-of, chart-cfd-stale-badge) for Playwright selectors. Outer wrapper always carries data-testid='chart-cfd'.
- Stale badge: rendered when Date.now() - as_of > 24h. Reuses the same bg-secondary / text-secondary-foreground tokens as AgileKpiStrip's approximation badge for visual consistency.
- Colors: Recharts SVG fill/stroke does not resolve var(--token) reliably, so chart palette is hard-coded hex from globals.css/DESIGN.md (chart-5 #5F7676 for todo, warning #E0A23B for in_progress, chart-3 #2D8380 for done, destructive #C0392B for cancelled, chart-4 #7BC9C0 fallback). The container (border, bg-card, muted-foreground text) still uses Tailwind tokens.
- Vietnamese labels via GROUP_LABELS map (todo -> Cho xu ly, in_progress -> Dang lam, done -> Hoan thanh, cancelled -> Da huy). Unknown groups fall back to the raw key so custom project groups still render.
- Recharts Tooltip formatter type is Formatter<ValueType, NameType> where ValueType = string | number | (string|number)[]. Declaring (value: number, name: string) fails tsc. Solution: omit param types and use typeof narrowing in the body (typeof value === 'number' ? value : String(value ?? '')). Avoids the banned 'as any' / @ts-ignore escape hatches.
- AreaChart uses stackId='cfd' on every <Area>, type='monotone', fillOpacity=0.65 for layered transparency without losing axis grid visibility. ResponsiveContainer width=100%, height=300; outer div also has h-[300px] so the empty container still occupies the grid cell before recharts mounts.
- Screen-reader fallback: a sr-only <table> with <caption>, <thead>, and per-day rows. Visually hidden but accessible to assistive tech, mirroring the chart's data exactly. Carries data-testid='chart-cfd-table-fallback'.
- Shell update: removed the cfd PLACEHOLDER_SECTIONS entry and rendered <AgileCfd data={null} loading={false} /> as the first child of the agile-dashboard-sections grid, so the CFD now occupies the first cell with the four remaining placeholders following.
- Verification: cd frontend && npx tsc --noEmit -> exit 0; cd frontend && npm run lint -> exit 0 (84 pre-existing warnings, zero in touched files). Evidence: .sisyphus/evidence/task-9-tsc.txt, .sisyphus/evidence/task-9-lint.txt. Commit bb4fc17.


## T10 — Aging WIP component (AgileAgingWip)

- `AdminDashboardRiskItem` in `frontend/src/lib/task-types.ts` and `app/schemas/tasks.py` is the **generic** `{id, title, severity, count, description}` shape — NOT the per-task `{task_id, task_title, state_name, age_days, warn_days, is_blocked, blocked_reason, assignee_name}` shape the plan implied. The T5 author chose the generic schema, and `MUST NOT modify task-types.ts` rules it out as a moving target. Adapted by:
  - Using `item.id` as the drill-down key + URL param + testid.
  - Using `item.count` as the age-day proxy for sort + display (`{count} ngày`).
  - Using `item.severity` string for the visual tier (danger / warning / neutral) since `age_days` / `warn_days` are not in the payload.
  - Treating `danger` severity as the blocked indicator surrogate.
- The admin tasks page reads the query param as `task` (not `task_id`) — see `frontend/src/app/(portal)/admin/tasks/page.tsx` line 150. The plan asked for `task_id` and I honoured it; future T14/wiring may want to either also accept `task_id` server-side or rename to `task` in this component.
- `AgileDashboardShell.tsx` placeholder list is hand-rolled: replacing one slot means removing it from `PLACEHOLDER_SECTIONS` AND inserting the real component inside the grid map (next to `<AgileCfd>`). Easy to miss step 2 and end up with two cards.
- Tailwind 4 JIT scans literal class strings, so kept all severity-tier classnames as full inline strings (`"border-l-destructive bg-destructive/5"`) — no template stitching, no dynamic class composition.
- Material Symbols Outlined available globally; reused `hourglass_top`, `block`, `arrow_forward` to stay consistent with the KPI strip + workspace-management link.
- `data-testid` naming inside the row uses `aging-risk-item-{id}-severity` / `-age` / `-blocked` so e2e specs can assert tier without scraping the className. Pattern matches the KPI strip convention.

## T11 — AgileThroughput chart (2026-05-18)

- **Recharts `<Tooltip content={Fn}>` typing**: when using a custom React-function tooltip with the unparameterised `<Tooltip />` element, the component prop must use the default `TooltipContentProps` generics (i.e. `({ active, payload }: TooltipContentProps) => ...`). Annotating `TooltipContentProps<number, string>` fails `tsc` because recharts narrows `ContentType<ValueType, NameType>` on the parent `<Tooltip>` — the narrower function is not assignable to that wider contract. Drop the generics or pass them through on `<Tooltip<number, string> />` (and `Bar<...>`) — the simpler fix is to drop them.
- **Bar onClick payload narrowing**: `recharts/types/cartesian/Bar.d.ts` types the callback as `(data: BarRectangleItem, index, event)` with `payload?: any`. You can therefore declare `handleBarClick(entry: { payload?: ChartRow })` directly and skip the unknown-narrowing dance, while still keeping `as any` out of the file.
- **Zero-completion bars stay visible**: don't filter `tasks_completed === 0` out of the throughput series. The brief explicitly wants empty bars rendered (not missing bars), and the empty-state copy only fires when the array length is 0.
- **Click-through URL contract**: `/admin/tasks?completed_from=...&completed_to=...` uses the raw `YYYY-MM-DD` ISO strings from `ThroughputDataPoint.period_start` / `period_end`. URL-encode them just in case the backend ever returns `HH:MM:SS` later.
- **Sibling component conventions to mirror** (from `AgileCfd.tsx` / `AgileAgingWip.tsx`): article wrapper with `data-testid`; skeleton when `loading || data === null`; disabled card when `!data.feature_enabled`; `stale` badge when `Date.now() - as_of > 24h`; `sr-only` `<table>` fallback so screen readers can read the chart; hard-coded hex colours because recharts SVG fills don't resolve `var(--token)` reliably.
- **Forbidden word check**: the `velocity` constraint applies to *any* occurrence in the file (including comments). Use `Select-String -CaseSensitive:$false` to verify before committing — a passing tsc/lint won't catch it.


## T12 - AgileBlockedPanel (2026-05-18)

- Severity tier reuse: copied the DANGER_SEVERITIES / WARNING_SEVERITIES Sets and the severityTier() / owAccentClass() / adgeClass() helper pattern from AgileAgingWip.tsx inline. No shared utility yet (none of the prior tasks extracted one); duplication is intentional per the brief ("copy pattern inline").
- Sort order differs from AgileAgingWip: T12 sorts by severity tier FIRST (danger -> warning -> neutral via TIER_RANK), then by count desc, then by Vietnamese-collated title. AgileAgingWip sorts by count desc only because every aging row is already in the same tier. Keep that distinction; do not "harmonise".
- MAX_VISIBLE_ROWS = 8 here vs. 10 in AgileAgingWip. Smaller cap keeps the blocked panel shorter so it stays scannable when paired next to the aging list in the lg:grid-cols-2 layout.
- Rows are non-clickable <li> elements (not <Link>). AdminDashboardRiskItem.id is opaque (could be a department, project, or aggregate bucket) so per-row drill-down would be misleading. Only the header "Xem t?t c?" -> /admin/tasks?blocked=true is a real navigation affordance.
- Empty/disabled copy MUST match the brief verbatim (Vietnamese diacritics included): empty = Không có r?i ro ho?c blocker nào du?c ghi nh?n., disabled = Tính nang chua du?c kích ho?t. Both end in a period unlike the AgingWip equivalents (Không có công vi?c nào t?n lâu. / Tính nang chua du?c kích ho?t) - small inconsistency, but follow the T12 spec exactly.
- Container data-testid='blocked-risk-panel' replaces the gile-section-blocked-placeholder testid the shell was emitting; e2e tests that previously asserted the placeholder will start failing once they pick up this change.
- Shell wiring required TWO edits: (1) remove the locked entry from PLACEHOLDER_SECTIONS, (2) insert <AgileBlockedPanel data={null} loading={false} /> in the sections grid before the .map(...). Forgetting step 1 leaves the placeholder card rendered alongside the real panel (already documented for T10, reconfirming).
- Verification: cd frontend && npx tsc --noEmit -> exit 0; cd frontend && npm run lint -> exit 0 (84 pre-existing warnings, zero in AgileBlockedPanel.tsx). Evidence: .sisyphus/evidence/task-12-tsc.txt, .sisyphus/evidence/task-12-lint.txt.

## T13 â€” AgileCapacityHeatmap (2026-05-18)
- Mirror the AgileBlockedPanel skeleton/disabled/empty/data branches for consistency across Agile dashboard sections.
- Sort capacity rows: overloaded first, then capacity_percent desc, fallback to vi locale label compare; unconfigured (null) sinks to bottom (treated as -1).
- Bar width clamps to 0-100% even if backend reports >100; use Math.min via clampPercent helper. Tailwind 4 inline width style is fine (no JIT scan needed for dynamic values).
- Tailwind tokens: bg-primary / border-l-primary for normal, bg-destructive / border-l-destructive / bg-destructive/5 for overloaded â€” both already present in globals.css per BIDV palette.
- AgileDashboardShell PLACEHOLDER_SECTIONS array deleted entirely (no remaining placeholders); rendered <AgileCapacityHeatmap data={null} loading={false} /> alongside the other five section components inside the grid.
- npm run lint: 0 errors, 84 pre-existing warnings (none in new files). npx tsc --noEmit: clean.

## T14 - Agile dashboard live data wiring (2026-05-18)
- `AgileDashboardShell.tsx` now owns the single admin dashboard fetch: `getAdminDashboardFlowSummary(dashboardParams)` runs on mount, range/filter changes, and manual refresh via a `refreshKey` counter.
- Range pills convert directly to API params with the required `today` / `start.setDate(today.getDate() - rangeDays)` pattern, then trim with `toISOString().split("T")[0]` for `YYYY-MM-DD`.
- Filter selects remain disabled because option population is a future task, but their local state is preserved and `cleanFilterParams()` omits null/empty ids before calling the API.
- Manual refresh uses `data-testid="dashboard-refresh"`; retry in the error card reuses the same refresh handler. Error branch hides the dashboard sections and shows the required Vietnamese failure copy.
- `data.as_of` is rendered below the filter bar with `data-testid="dashboard-as-of"` and formatted via `Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" })`.
- All six child dashboard components now receive `{ data: dashboardData, loading: dashboardLoading }` from the shell; no child components were modified.
- LSP diagnostics could not run because `typescript-language-server` is not installed on this Windows host; `cd frontend && npx tsc --noEmit` is clean and saved to `.sisyphus/evidence/task-14-tsc.txt`.
- `cd frontend && npm run lint` exits 0 and is saved to `.sisyphus/evidence/task-14-lint.txt`; warnings are pre-existing and not in `AgileDashboardShell.tsx`.

## Task 16 - Admin dashboard API edge coverage (2026-05-18)
- Extended `tests/api/test_admin_dashboard_router.py` in place; no router/service changes were needed.
- The dashboard seed now returns workspace handles plus helper callables so extra TaskProject rows can be created inside one existing workspace for isolated API assertions.
- For query-count protection, attach a SQLAlchemy `before_cursor_execute` listener to `db_session.get_bind()` around only the flow-summary request, then remove it in `finally`; filter SAVEPOINT/RELEASE noise and assert the request stays under 10 SQL statements.
- Admin users see all historical projects in a shared dev database, so tests that assert exact `scoped_project_count` should pass a workspace_id/project_id filter tied to freshly seeded rows.
- Host Python/pytest were unavailable on this Windows host; verification ran in the `api` Docker service after copying the updated test file into `/app`. Evidence saved to `.sisyphus/evidence/task-16-pytest.txt`.
- `ruff` was not installed in the API image by default; installed it in the running container and `ruff check app/ alembic/ tests/` passed.


## Task 15: Agile Dashboard Playwright spec (2026-05-18)

- Wrote rontend/tests/admin-dashboard.spec.ts covering 8 scenarios:
  toggle-classic-agile, kpi-strip-renders, approximation-badge,
  feature-disabled-state, range-filter-triggers-request, manual-refresh,
  aging-drill-down, no-velocity-in-copy.
- Pattern: page.route('**/api/admin/dashboard/flow-summary*', …) returns a
  typed `FlowSummary` happy-path matching `AdminDashboardFlowSummaryResponse`
  in `src/lib/task-types.ts`. Overrides via `buildHappyPath({...})`.
- KPI cards live inside `AgileKpiStrip`; testids are `kpi-wip`,
  `kpi-blocked`, `kpi-aging`, `kpi-throughput`, `kpi-cycle-time`,
  `kpi-lead-time`. Risk rows are `aging-risk-item-<id>`. Approximation
  badge uses Vietnamese label "S? li?u x?p x?".
- `ClassicDashboardView` exposes `data-testid="classic-dashboard-root"`
  (mounted automatically when `view` query param is missing / "classic").
- Skip guard: when the running Docker stack predates the Agile shell
  (no `dashboard-view-toggle` on /admin) the whole suite `test.skip`s
  with a hint to rebuild the frontend container. Same guard catches the
  "stack offline" case via login failure.
- Verified by running `docker compose up -d --build frontend` then
  `cd frontend && npm run test:e2e -- --project=chromium admin-dashboard.spec.ts`.
  All 8 tests pass in ~43s.
- Evidence: `.sisyphus/evidence/task-15-playwright.txt`.



---

## Task 17 â€” Dashboard quality audit (2026-05-18)

**Tooling baselines (all green, no fixes required):**
- `npm run lint` -> exit 0, 84 warnings, 0 errors. The 84 warnings are pre-existing project-wide patterns (`react-hooks/set-state-in-effect` etc.) that AGENTS.md deliberately keeps at `warn` and tells you to fix only when touching the file. None come from the new `components/admin/dashboard/` files for net-new logic â€” `ClassicDashboardView.tsx` is a verbatim legacy lift.
- `npx tsc --noEmit` -> exit 0, no output. Never use `npm run build` to typecheck (`typescript.ignoreBuildErrors: true`).

**Forbidden-term sweep â€” pattern works:**
`Select-String -Path "frontend\src\components\admin\dashboard\*.tsx" -Pattern 'velocity|burndown|forecast|leaderboard|Monte Carlo|retrospective' -CaseSensitive:False`
Returns 0 matches on the current dashboard set. Bake this into any future PR check that adds dashboard widgets.

**Accessibility patterns that landed correctly in T8-T13 (re-use them):**
- Recharts charts: wrap `ResponsiveContainer` in `<div role="img" aria-label="...">` AND ship a paired `<table class="sr-only">` with `<caption>`, `<th scope="col">`, `<th scope="row">` mirroring the data. `AgileCfd` and `AgileThroughput` show the canonical shape.
- Loading skeletons: every section sets `aria-busy="true"` + Vietnamese `aria-label` on the wrapper and `aria-hidden` on the pulse divs.
- Capacity bars use native `role="progressbar"` with `aria-valuenow/min/max/label` â€” semantically richer than a chart wrapper, prefer it whenever the visual is a percent bar.
- Severity is never color-only: badges always render Vietnamese label text ("Nguy cáº¥p", "Cáº£nh bÃ¡o", "Theo dÃµi", "QuÃ¡ táº£i") and a Material icon. Don't drop the badge even if the row already has a destructive border.
- Recharts paints raw SVG `fill`/`stroke` attributes that don't resolve `var(--token)` across browsers â€” hard-code the BIDV hex palette in chart files (already done: `#2D8380` teal, `#E0A23B` amber, `#C0392B` destructive, `#5F7676` slate). Keep this convention for any new chart.

**Bundle delta:**
- Init commit (4276622) had no `recharts`; current adds `recharts ^3.8.1` (~60-70 KB gz). Added in commit `b522649 chore(dashboard): validate chart stack`.
- No other new runtime deps for the dashboard. `d3-drag`/`d3-force` were already present for the wiki graph.

**Known doc/spec drift (don't be confused by it):**
- Inherited wisdom says `AgileBlockedPanel` uses `data-testid="risk-panel"`. The live component uses `data-testid="blocked-risk-panel"` and the Playwright spec already matches the live id. Believe the code.

**Recharts `<Bar onClick>` keyboard gap:** SVG bars in Recharts don't receive focus by default. The sr-only fallback table + the visible date-range pills already give keyboard users a path to the same drilldown URLs. If a future iteration needs true keyboard activation on each bar, render an off-screen `<button>` per period with the same handler.


## T18 â€” Dashboard resilience hardening (2026-05-18)
- Each widget (AgileKpiStrip / AgileCfd / AgileAgingWip / AgileThroughput / AgileBlockedPanel / AgileCapacityHeatmap) now accepts optional `error?: boolean` + `onRetry?: () => void` props. Error wins over skeleton: when `error && data === null && !loading`, render a destructive-border card with Vietnamese "KhÃ´ng thá»ƒ táº£i dá»¯ liá»‡u" copy and a "Thá»­ láº¡i" refresh button.
- TS narrowing pitfall: extracting `const showSkeleton = !showError && (loading || data === null)` into a variable BREAKS narrowing â€” TS18047 "data is possibly null" fires in every later branch. Fix: keep the direct `if (loading || data === null) { return <Skeleton/>; }` after the error branch so TS can narrow `data` to non-null. `showError` as a computed boolean is fine because the error branch returns early before the data-dependent code.
- Shell change: removed the unified `data-testid="dashboard-error"` block (was a full-page replacement) and now passes `error={dashboardError}` + `onRetry={handleRefresh}` to every widget. One failed fetch keeps the filters/KPIs/charts mounted; each widget reports failure independently.
- Stale-data shell banner: `data-testid="stale-data-warning"` rendered when `dashboardData && Date.now() - new Date(dashboardData.as_of).getTime() > 24h`. Amber palette (`border-amber-400/60 bg-amber-50 text-amber-900`) to distinguish from destructive widget errors. Inline `isStale()` helper mirrors the per-widget badges in AgileCfd / AgileThroughput.
- Added testids: `chart-throughput-error` + `chart-throughput-retry` (required by T15 e2e), plus parallel `chart-cfd-error/retry`, `chart-aging-wip-error/retry`, `blocked-risk-panel-error/retry`, `capacity-heatmap-error/retry`, `agile-kpi-strip-error/retry` for symmetry.
- Preserved existing T15 testids: `agile-kpi-strip-disabled`, `chart-aging-wip`, `blocked-risk-panel`, `chart-cfd`, `chart-throughput`, `capacity-heatmap`. All widget root testids stay even in error mode.
- Verification: `npx tsc --noEmit` -> exit 0; `npm run lint` -> exit 0 (84 pre-existing warnings, zero in touched files). Evidence: `.sisyphus/evidence/task-18-tsc.txt`, `.sisyphus/evidence/task-18-lint.txt`. Commit 3bff808.

## Task 20 — Verification suite (2026-05-18)
- Verification-only run saved combined evidence to .sisyphus/evidence/task-20-verification-suite.txt and screenshot to .sisyphus/evidence/task-20-runtime-dashboard.png; no fixes and no commit.
- Docker runtime containers are production-lean: api lacks pytest (pytest not on PATH, python -m pytest says no module), frontend lacks eslint/typescript/playwright. For verification from the current stack, host fallbacks worked for frontend lint/tsc/e2e; backend pytest needs a dev/test image or deps copied/installed as in Task 16.
- Runtime QA confirms Agile dashboard loads at /admin?view=agile and shows gile-dashboard-root, kpi-wip, and chart-cfd; exact selector isk-panel is absent because the shipped component uses locked-risk-panel (same drift noted in Task 17).
- Overall Task 20 verdict: FAIL/BLOCKED because backend pytest could not run in available environments and the requested isk-panel selector is missing, despite ruff/frontend host lint/tsc/e2e passing.

- [2026-05-18] Updated admin dashboard Playwright expectations so /admin now defaults to Agile; no dashboard copy mentions a default view.

