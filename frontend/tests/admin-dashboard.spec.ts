import { test, expect, type Page, type Route, type Request } from '@playwright/test';

/**
 * Agile Flow Command Center dashboard — Playwright e2e (Task 15).
 *
 * Covers the eight scenarios called out in the task spec:
 *   1. toggle-classic-agile
 *   2. kpi-strip-renders
 *   3. approximation-badge
 *   4. feature-disabled-state
 *   5. range-filter-triggers-request
 *   6. manual-refresh
 *   7. aging-drill-down
 *   8. no-velocity-in-copy
 *
 * Tests mock `/api/admin/dashboard/flow-summary*` deterministically via
 * `page.route()` so state-specific assertions never depend on the live
 * backend. The mock shape matches `AdminDashboardFlowSummaryResponse` from
 * `frontend/src/lib/task-types.ts`.
 *
 * Targets the Docker stack at http://localhost:3119 (overridable via
 * E2E_BASE_URL). If the login page fails to load (Docker stack absent),
 * each test `test.skip`s with an explanatory annotation rather than
 * failing.
 */

const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? 'admin@cmdsupport.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? 'cmd@1234';

type FlowSummary = {
  feature_enabled: boolean;
  as_of: string;
  approximation_used: boolean;
  scoped_project_count: number;
  wip_count: number;
  blocked_count: number;
  aging_count: number;
  throughput_count: number;
  cycle_time_p50: number;
  lead_time_p50: number;
  chart_series: {
    cfd_series: Array<{
      snapshot_date: string;
      state_counts: Record<string, number>;
      blocked_count: number;
    }>;
    aging_tasks: Array<{
      task_id: string | null;
      title: string;
      state_name: string;
      aging_days: number;
      priority: string | null;
      assignee_names: string[];
    }>;
    throughput_series: Array<{
      period_start: string;
      period_end: string;
      tasks_completed: number;
      story_points_completed: number;
    }>;
  };
  risk_items: Array<{
    id: string;
    title: string;
    severity: string;
    count: number;
    description: string | null;
  }>;
  capacity_items: Array<{
    id: string;
    label: string;
    capacity_percent: number | null;
    open_task_count: number;
    story_points_sum: number | null;
    is_overloaded: boolean;
  }>;
};

function buildHappyPath(overrides: Partial<FlowSummary> = {}): FlowSummary {
  return {
    feature_enabled: true,
    as_of: new Date('2026-05-18T08:00:00.000Z').toISOString(),
    approximation_used: false,
    scoped_project_count: 2,
    wip_count: 5,
    blocked_count: 1,
    aging_count: 2,
    throughput_count: 8,
    cycle_time_p50: 3.2,
    lead_time_p50: 5.1,
    chart_series: {
      cfd_series: [],
      aging_tasks: [],
      throughput_series: [],
    },
    risk_items: [],
    capacity_items: [],
    ...overrides,
  };
}

async function installFlowSummaryRoute(
  page: Page,
  payloadFactory: () => FlowSummary,
  options: { onRequest?: (request: Request) => void } = {},
): Promise<void> {
  await page.route('**/api/admin/dashboard/flow-summary*', async (route: Route) => {
    options.onRequest?.(route.request());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payloadFactory()),
    });
  });
}

async function loginAsAdmin(page: Page): Promise<boolean> {
  try {
    await page.goto('/login', { timeout: 15_000 });
  } catch {
    return false;
  }
  if (!/\/login$/.test(page.url())) {
    return false;
  }
  await page.locator('#email').fill(ADMIN_EMAIL);
  await page.locator('#password').fill(ADMIN_PASSWORD);
  try {
    await Promise.all([
      page.waitForURL(/\/admin(\/.*)?$/, { timeout: 15_000 }),
      page.getByRole('button', { name: /đăng nhập/i }).click(),
    ]);
  } catch {
    return false;
  }
  return /\/admin(\/.*)?$/.test(page.url());
}

async function gotoAgile(page: Page): Promise<void> {
  await page.goto('/admin?view=agile');
  await expect(page.getByTestId('agile-dashboard-root')).toBeVisible();
}

/**
 * The Agile shell + view-toggle ship as part of the Phase 5 dashboard. When
 * the running Docker stack predates that work (typical during local dev
 * before `docker compose up -d --build`), `/admin` still renders the old
 * single-view layout without `dashboard-view-classic` / `agile-dashboard-root`.
 * Probe for the toggle once and skip the whole suite when it is absent —
 * tests would otherwise fail noisily against an environment that has no
 * way to satisfy them.
 */
async function probeAgileShellDeployed(page: Page): Promise<boolean> {
  await page.goto('/admin');
  const toggle = page.getByTestId('dashboard-view-toggle');
  try {
    await toggle.waitFor({ state: 'attached', timeout: 5_000 });
    return true;
  } catch {
    return false;
  }
}

test.describe('admin agile dashboard', () => {
  test.beforeEach(async ({ page }) => {
    // The Agile shell calls the flow-summary endpoint as soon as it mounts.
    // Install a default happy-path mock for tests that don't override it so
    // `page.goto('/admin?view=agile')` never races against a 404 / 500 from
    // a partially-seeded backend.
    await installFlowSummaryRoute(page, () => buildHappyPath());

    const loggedIn = await loginAsAdmin(page);
    test.skip(
      !loggedIn,
      'Docker stack on :3119 (or E2E_BASE_URL) not reachable — admin login failed.',
    );

    const deployed = await probeAgileShellDeployed(page);
    test.skip(
      !deployed,
      'Agile dashboard shell not deployed on the running stack — rebuild the frontend container (docker compose up -d --build frontend) to exercise this suite.',
    );
  });

  test('toggle-classic-agile switches dashboard view', async ({ page }) => {
    await page.goto('/admin');

    // Classic is the default view.
    await expect(page.getByTestId('classic-dashboard-root')).toBeVisible();
    await expect(page.getByTestId('agile-dashboard-root')).toHaveCount(0);

    await page.getByTestId('dashboard-view-agile').click();
    await expect(page.getByTestId('agile-dashboard-root')).toBeVisible();

    await page.getByTestId('dashboard-view-classic').click();
    await expect(page.getByTestId('classic-dashboard-root')).toBeVisible();
    await expect(page.getByTestId('agile-dashboard-root')).toHaveCount(0);
  });

  test('kpi-strip-renders shows all six KPI cards', async ({ page }) => {
    await gotoAgile(page);

    const testIds = [
      'kpi-wip',
      'kpi-blocked',
      'kpi-aging',
      'kpi-throughput',
      'kpi-cycle-time',
      'kpi-lead-time',
    ];

    for (const id of testIds) {
      await expect(page.getByTestId(id)).toBeVisible();
    }
  });

  test('approximation-badge appears when approximation_used=true', async ({ page }) => {
    await page.unroute('**/api/admin/dashboard/flow-summary*');
    await installFlowSummaryRoute(page, () =>
      buildHappyPath({ approximation_used: true }),
    );

    await gotoAgile(page);

    await expect(page.getByText('Số liệu xấp xỉ').first()).toBeVisible();
  });

  test('feature-disabled-state renders disabled message and no KPI values', async ({
    page,
  }) => {
    await page.unroute('**/api/admin/dashboard/flow-summary*');
    await installFlowSummaryRoute(page, () =>
      buildHappyPath({
        feature_enabled: false,
        wip_count: 0,
        blocked_count: 0,
        aging_count: 0,
        throughput_count: 0,
        cycle_time_p50: 0,
        lead_time_p50: 0,
      }),
    );

    await gotoAgile(page);

    await expect(page.getByTestId('agile-kpi-strip-disabled')).toBeVisible();
    await expect(
      page.getByText('Tính năng Agile chưa được kích hoạt'),
    ).toBeVisible();
    // None of the live KPI cards should mount.
    await expect(page.getByTestId('kpi-wip')).toHaveCount(0);
    await expect(page.getByTestId('kpi-throughput')).toHaveCount(0);
  });

  test('range-filter-triggers-request appends start_date param', async ({ page }) => {
    await gotoAgile(page);

    const requestPromise = page.waitForRequest((req) =>
      req.url().includes('/api/admin/dashboard/flow-summary') &&
      req.url().includes('start_date='),
    );

    await page.getByTestId('dashboard-range-7d').click();
    const request = await requestPromise;
    expect(request.url()).toContain('start_date=');
  });

  test('manual-refresh re-sends the flow-summary request', async ({ page }) => {
    let requestCount = 0;
    await page.unroute('**/api/admin/dashboard/flow-summary*');
    await installFlowSummaryRoute(page, () => buildHappyPath(), {
      onRequest: () => {
        requestCount += 1;
      },
    });

    await gotoAgile(page);
    // Wait for the mount-time fetch to settle so we count refreshes cleanly.
    await expect(page.getByTestId('kpi-wip')).toBeVisible();
    const beforeRefresh = requestCount;

    const refreshRequest = page.waitForRequest((req) =>
      req.url().includes('/api/admin/dashboard/flow-summary'),
    );
    await page.getByTestId('dashboard-refresh').click();
    await refreshRequest;

    expect(requestCount).toBeGreaterThan(beforeRefresh);
  });

  test('aging-drill-down navigates to /admin/tasks from a risk row', async ({
    page,
  }) => {
    await page.unroute('**/api/admin/dashboard/flow-summary*');
    await installFlowSummaryRoute(page, () =>
      buildHappyPath({
        risk_items: [
          {
            id: 'task-aged-001',
            title: 'Tài liệu giả lập tồn lâu',
            severity: 'high',
            count: 12,
            description: 'Chờ duyệt quá hạn',
          },
        ],
      }),
    );

    await gotoAgile(page);

    await expect(page.getByTestId('chart-aging-wip')).toBeVisible();

    const row = page.getByTestId('aging-risk-item-task-aged-001');
    await expect(row).toBeVisible();
    await row.click();

    await page.waitForURL(/\/admin\/tasks(\?.*)?$/);
    expect(page.url()).toMatch(/\/admin\/tasks/);
  });

  test('no-velocity-in-copy — "velocity" never appears on the Agile dashboard', async ({
    page,
  }) => {
    await gotoAgile(page);
    // Wait for the KPI strip so we're sure copy is fully rendered before
    // grepping the page text.
    await expect(page.getByTestId('kpi-wip')).toBeVisible();

    const bodyText = await page.locator('body').innerText();
    expect(bodyText.toLowerCase()).not.toContain('velocity');
  });
});
