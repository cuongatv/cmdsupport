import { test, expect, type Page, type Route, type Request } from '@playwright/test';
import path from 'node:path';

/**
 * Native task management — negative-path Playwright suite (T29).
 *
 * Targets the Docker stack at http://localhost:3119 (overridable via
 * E2E_BASE_URL). Logs in as the default admin and then mocks the relevant
 * API surface to exercise permission gating, optimistic-concurrency 409
 * handling, and forbidden attachment validation. Asserts no `/api/plane*`
 * requests in any scenario.
 */

const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? 'admin@cmdsupport.com';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? 'cmd@1234';

const EVIDENCE_DIR =
  process.env.T29_NEGATIVE_EVIDENCE_DIR ??
  path.resolve(
    __dirname,
    '..',
    '..',
    '.sisyphus',
    'evidence',
    'task-29-playwright-negative'
  );

const SUITE_ID = `t29n-${Date.now().toString(36)}`;
const SUITE_PROJECT_IDENTIFIER = `T29N${Date.now().toString(36).slice(-5).toUpperCase()}`;
const SUITE_PROJECT_NAME = `T29 negative ${SUITE_ID}`;
const SUITE_TASK_TITLE = `T29 negative task ${SUITE_ID}`;

let suiteProjectId = '';
let suiteTaskId = '';

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

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

type PlaneGuard = {
  hits: string[];
  cleanup: () => Promise<void>;
};

async function installPlaneGuard(page: Page): Promise<PlaneGuard> {
  const hits: string[] = [];
  await page.route('**/api/plane**', (route: Route, request: Request) => {
    hits.push(`${request.method()} ${request.url()}`);
    route.fulfill({
      status: 599,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'native task suite forbids plane' }),
    });
  });
  return {
    hits,
    cleanup: async () => {
      await page.unroute('**/api/plane**').catch(() => {});
    },
  };
}

type ApiResponse = { status: number; body: unknown };

async function apiCall(
  page: Page,
  pathname: string,
  init?: { method?: string; body?: unknown }
): Promise<ApiResponse> {
  const baseUrl = (
    process.env.E2E_API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    'http://localhost:5055'
  ).replace(/\/$/, '');
  return page.evaluate<ApiResponse, { url: string; method: string; body: string | null }>(
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
      let parsed: unknown = null;
      try {
        parsed = await res.json();
      } catch {
        parsed = null;
      }
      return { status: res.status, body: parsed };
    },
    {
      url: `${baseUrl}${pathname}`,
      method: init?.method ?? 'GET',
      body: init?.body !== undefined ? JSON.stringify(init.body) : null,
    }
  );
}

type ScopeOption = { id: string; name: string };

async function pickScope(page: Page): Promise<{ id: string; isWorkspace: boolean }> {
  const workspaces = await apiCall(page, '/api/projects');
  if (workspaces.status === 200 && Array.isArray(workspaces.body) && workspaces.body.length > 0) {
    return { id: (workspaces.body[0] as ScopeOption).id, isWorkspace: true };
  }
  const departments = await apiCall(page, '/api/departments');
  if (departments.status === 200 && Array.isArray(departments.body) && departments.body.length > 0) {
    return { id: (departments.body[0] as ScopeOption).id, isWorkspace: false };
  }
  throw new Error('No workspace or department available to scope a task project');
}

async function ensureFixture(page: Page): Promise<void> {
  if (suiteProjectId !== '' && suiteTaskId !== '') return;
  const scope = await pickScope(page);
  const projectRes = await apiCall(page, '/api/tasks/projects', {
    method: 'POST',
    body: {
      name: SUITE_PROJECT_NAME,
      identifier: SUITE_PROJECT_IDENTIFIER,
      description: 'T29 negative-path Playwright fixture',
      workspace_id: scope.isWorkspace ? scope.id : null,
      department_id: scope.isWorkspace ? null : scope.id,
      allow_any_employee: true,
    },
  });
  if (projectRes.status >= 400 || !projectRes.body) {
    throw new Error(
      `Project create failed: status=${projectRes.status} body=${JSON.stringify(projectRes.body)}`
    );
  }
  suiteProjectId = (projectRes.body as { id: string }).id;

  const states = await apiCall(page, `/api/tasks/projects/${suiteProjectId}/states`);
  const stateId = Array.isArray(states.body)
    ? (states.body[0] as { id: string }).id
    : '';
  const taskRes = await apiCall(
    page,
    `/api/tasks?task_project_id=${encodeURIComponent(suiteProjectId)}`,
    {
      method: 'POST',
      body: {
        title: SUITE_TASK_TITLE,
        description: 'T29 negative fixture task',
        priority: 'medium',
        state_id: stateId,
        reporter_id: null,
        parent_task_id: null,
        due_date: null,
        assignee_ids: [],
        label_ids: [],
      },
    }
  );
  if (taskRes.status >= 400 || !taskRes.body) {
    throw new Error(
      `Task create failed: status=${taskRes.status} body=${JSON.stringify(taskRes.body)}`
    );
  }
  suiteTaskId = (taskRes.body as { id: string }).id;
}

async function saveScreenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, `${name}.png`),
    fullPage: true,
  });
}

/* ------------------------------------------------------------------ */
/* Suite                                                               */
/* ------------------------------------------------------------------ */

test.describe.serial('Native tasks — negative path', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await login(page);
    await ensureFixture(page);
    await context.close();
  });

  let guard: PlaneGuard;

  test.beforeEach(async ({ page }) => {
    guard = await installPlaneGuard(page);
    await login(page);
  });

  test.afterEach(async ({ page }, testInfo) => {
    expect(
      guard.hits,
      `Expected zero /api/plane* requests, observed:\n${guard.hits.join('\n')}`
    ).toEqual([]);
    await saveScreenshot(
      page,
      testInfo.title.replace(/[^a-z0-9]+/gi, '-').toLowerCase()
    );
    await guard.cleanup();
  });

  test('hides task nav for users without task:read permission', async ({ page }) => {
    // Mock /api/auth/me so the AuthProvider sees a non-admin employee with
    // zero task permissions on the next refresh().
    await page.route('**/api/auth/me', async (route) => {
      const original = await route.fetch();
      let json: Record<string, unknown> | null = null;
      try {
        json = (await original.json()) as Record<string, unknown>;
      } catch {
        json = null;
      }
      if (!json) {
        await route.continue();
        return;
      }
      const filtered = {
        ...json,
        role: 'employee',
        permissions: Array.isArray(json.permissions)
          ? (json.permissions as string[]).filter(
              (p) => !p.startsWith('task:') && !p.startsWith('task_project:')
            )
          : [],
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(filtered),
      });
    });

    await page.goto('/admin');
    // Wait for the sidebar to render (an org-level item that always shows for
    // the mocked employee — the dashboard link is rendered unconditionally).
    await page.waitForSelector('nav a[href="/admin"]', { timeout: 15_000 });

    // Sidebar nav for native tasks must be hidden.
    await expect(page.locator('nav a[href="/admin/tasks"]')).toHaveCount(0);
    await expect(page.locator('nav').getByText('Quản lý công việc')).toHaveCount(0);

    // Direct URL access also bounces with the access-denied notice.
    await page.goto('/admin/tasks');
    await expect(
      page.getByText('Bạn không có quyền truy cập danh sách công việc.')
    ).toBeVisible({ timeout: 15_000 });
  });

  test('shows version-conflict (409) message when a task PATCH is stale', async ({
    page,
  }) => {
    await ensureFixture(page);
    await page.route('**/api/tasks/*', async (route, request) => {
      if (request.method() === 'PATCH') {
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'version conflict' }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto(
      `/admin/tasks?task_project_id=${encodeURIComponent(suiteProjectId)}`
    );
    await page.waitForSelector(`[data-testid="task-row-${suiteTaskId}"]`, {
      timeout: 15_000,
    });
    await page.locator(`[data-testid="task-row-${suiteTaskId}"]`).click();
    await page.waitForSelector('[data-testid="task-detail-edit-btn"]', {
      timeout: 10_000,
    });
    await page.click('[data-testid="task-detail-edit-btn"]');
    await page.waitForSelector('[data-testid="task-dialog-title-input"]', {
      timeout: 5_000,
    });
    await page.fill(
      '[data-testid="task-dialog-title-input"]',
      `${SUITE_TASK_TITLE} (stale edit)`
    );
    await page.click('[data-testid="task-dialog-save-btn"]');

    const error = page.locator('[data-testid="task-dialog-form-error"]');
    await expect(error).toBeVisible({ timeout: 10_000 });
    await expect(error).toContainText(
      'công việc đã được cập nhật bởi người khác'
    );
  });

  test('rejects forbidden attachment type (.exe)', async ({ page }) => {
    await ensureFixture(page);
    await page.goto(
      `/admin/tasks?task_project_id=${encodeURIComponent(suiteProjectId)}`
    );
    await page.waitForSelector(`[data-testid="task-row-${suiteTaskId}"]`, {
      timeout: 15_000,
    });
    await page.locator(`[data-testid="task-row-${suiteTaskId}"]`).click();
    await page.waitForSelector('[data-testid="task-detail-tab-attachments"]', {
      timeout: 10_000,
    });
    await page.click('[data-testid="task-detail-tab-attachments"]');

    // Use the file-chooser pattern: the real input is `display: none`, so the
    // upload button click is what triggers the OS picker in production. This
    // surfaces the change event reliably across browsers.
    const chooserPromise = page.waitForEvent('filechooser');
    await page.click('[data-testid="task-attachment-upload-btn"]');
    const chooser = await chooserPromise;
    await chooser.setFiles({
      name: `t29-${SUITE_ID}.exe`,
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('not actually an executable'),
    });

    const err = page.locator('[data-testid="task-attachment-error"]');
    await expect(err).toBeVisible({ timeout: 10_000 });
    await expect(err).toContainText('loại tệp không được phép');
  });
});
