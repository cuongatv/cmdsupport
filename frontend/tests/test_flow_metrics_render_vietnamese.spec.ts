import { test, expect, type Page, type Route, type Request } from '@playwright/test';

const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? 'admin@cmdsupport.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? 'cmd@1234';
const API_BASE_URL = (
  process.env.E2E_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:5055'
).replace(/\/$/, '');

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await expect(page).toHaveURL(/\/login$/);
  await page.locator('#email').fill(ADMIN_EMAIL);
  await page.locator('#password').fill(ADMIN_PASSWORD);
  await Promise.all([
    page.waitForURL(/\/admin(\/.*)?$/, { timeout: 15_000 }),
    page.getByRole('button', { name: /đăng nhập/i }).click(),
  ]);
}

type ApiResponse<T> = { status: number; body: T | null };

async function apiCall<T>(
  page: Page,
  pathname: string,
  init?: { method?: string; body?: unknown }
): Promise<ApiResponse<T>> {
  return page.evaluate<ApiResponse<T>, { url: string; method: string; body: string | null }>(
    async ({ url, method, body }) => {
      const token = window.localStorage.getItem('cmd_support_token');
      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: body ?? undefined,
      });
      let parsed: T | null = null;
      try {
        parsed = (await res.json()) as T;
      } catch {
        parsed = null;
      }
      return { status: res.status, body: parsed };
    },
    {
      url: `${API_BASE_URL}${pathname}`,
      method: init?.method ?? 'GET',
      body: init?.body !== undefined ? JSON.stringify(init.body) : null,
    }
  );
}

type ScopeOption = { id: string; name: string };
type TaskProject = { id: string; identifier: string; name: string };
type TaskState = { id: string; name: string };
type Task = { id: string; version: number };

async function pickScope(page: Page): Promise<{ id: string; isWorkspace: boolean }> {
  const workspaces = await apiCall<ScopeOption[]>(page, '/api/projects');
  if (workspaces.status === 200 && Array.isArray(workspaces.body) && workspaces.body.length > 0) {
    return { id: workspaces.body[0].id, isWorkspace: true };
  }
  const departments = await apiCall<ScopeOption[]>(page, '/api/departments');
  if (departments.status === 200 && Array.isArray(departments.body) && departments.body.length > 0) {
    return { id: departments.body[0].id, isWorkspace: false };
  }
  throw new Error('No workspace or department available for Phase 5 flow metrics fixture');
}

async function createProject(page: Page): Promise<TaskProject> {
  const scope = await pickScope(page);
  const suffix = Date.now().toString(36).slice(-6).toUpperCase();
  const res = await apiCall<TaskProject>(page, '/api/tasks/projects', {
    method: 'POST',
    body: {
      name: `Phase 5 flow metrics ${suffix}`,
      identifier: `P5F${suffix.slice(-5)}`,
      workspace_id: scope.isWorkspace ? scope.id : null,
      department_id: scope.isWorkspace ? null : scope.id,
      allow_any_employee: true,
    },
  });
  if (res.status >= 400 || !res.body) {
    throw new Error(`Project create failed: status=${res.status} body=${JSON.stringify(res.body)}`);
  }
  return res.body;
}

async function createTask(page: Page, projectId: string): Promise<Task> {
  const states = await apiCall<TaskState[]>(page, `/api/tasks/projects/${projectId}/states`);
  const stateId = Array.isArray(states.body) && states.body[0]?.id ? states.body[0].id : '';
  if (!stateId) throw new Error('No state available for Phase 5 flow metrics fixture');
  const res = await apiCall<Task>(page, `/api/tasks?task_project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
    body: {
      title: `Phase 5 Vietnamese metrics task ${Date.now().toString(36)}`,
      priority: 'medium',
      state_id: stateId,
      assignee_ids: [],
      label_ids: [],
    },
  });
  if (res.status >= 400 || !res.body) {
    throw new Error(`Task create failed: status=${res.status} body=${JSON.stringify(res.body)}`);
  }
  return res.body;
}

async function installMetricsRoutes(page: Page): Promise<void> {
  await page.route('**/api/task-projects/*/flow-metrics?**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'snapshot-todo',
          task_project_id: 'project-fixture',
          snapshot_date: '2026-05-17',
          state_id: 'state-todo',
          task_count: 4,
          story_points_sum: 8,
          blocked_count: 1,
          created_at: '2026-05-17T00:00:00Z',
        },
        {
          id: 'snapshot-doing',
          task_project_id: 'project-fixture',
          snapshot_date: '2026-05-17',
          state_id: 'state-doing',
          task_count: 2,
          story_points_sum: 5,
          blocked_count: 1,
          created_at: '2026-05-17T00:00:00Z',
        },
      ]),
    });
  });
  await page.route('**/api/task-projects/*/throughput?**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ tasks_completed: 3, story_points_completed: 13 }),
    });
  });
}

test('flow metrics render Vietnamese labels and no out-of-scope charts', async ({ page }) => {
  await login(page);
  const project = await createProject(page);
  await createTask(page, project.id);
  await installMetricsRoutes(page);

  await page.goto(`/admin/tasks/projects/${project.id}`);
  await expect(page.getByTestId('flow-metrics-panel')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Chỉ số dòng chảy công việc' })).toBeVisible();
  await expect(page.getByTestId('flow-metric-lead-time')).toContainText('Thời gian xử lý');
  await expect(page.getByTestId('flow-metric-cycle-time')).toContainText('Thời gian hoàn tất');
  await expect(page.getByTestId('flow-metric-throughput')).toContainText('Số việc hoàn thành');
  await expect(page.getByTestId('flow-metric-throughput')).toContainText('3');
  await expect(page.getByTestId('flow-metric-blocked')).toContainText('Công việc đang bị chặn');
  await expect(page.getByTestId('flow-metrics-governance')).toContainText('Quy tắc điều phối');

  const panelText = await page.getByTestId('flow-metrics-panel').innerText();
  expect(panelText).not.toMatch(/burn.?down chart|velocity chart|forecast/i);
});
