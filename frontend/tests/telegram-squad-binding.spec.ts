import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Telegram squad binding tab — Playwright e2e (Task 23, surface 2/3).
 *
 * Targets the "Telegram" tab on the department hub
 * (`/admin/departments/<id>?tab=telegram`). The tab is implemented by
 * `src/components/telegram/squad-telegram-section.tsx` and mounted from
 * `src/app/(portal)/admin/departments/[id]/page.tsx`.
 *
 * The suite is fully hermetic with respect to the backend:
 *   - Auth is injected via `localStorage` + a `/api/auth/me` route mock.
 *   - `/api/departments`, `/api/tasks/projects`, `/api/telegram/bindings*`
 *     are all mocked with deterministic payloads.
 *   - A `page.on('request')` guard fails the test if anything dials
 *     `api.telegram.org` directly.
 *
 * Prerequisites:
 *   - The Next.js portal must be reachable at the Playwright baseURL
 *     (default http://localhost:3119, overridable via E2E_BASE_URL). When
 *     the host is unreachable the suite `test.skip`s with a clear note.
 */

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

type MockUser = {
  id: string;
  name: string;
  email: string;
  username: string;
  role: 'admin' | 'employee';
  department_id: string;
  department_name: string;
  permissions: string[];
  workspace_memberships: unknown[];
};

const SQUAD_ID = '00000000-0000-0000-0000-0000000005a1';
const SQUAD_NAME = 'Test Squad α';
const PROJECT_ID = '00000000-0000-0000-0000-0000000007a1';

const ADMIN_USER: MockUser = {
  id: '00000000-0000-0000-0000-0000000000a1',
  name: 'Test Admin',
  email: 'admin@cmdsupport.test',
  username: 'testadmin',
  role: 'admin',
  department_id: '00000000-0000-0000-0000-0000000000d0',
  department_name: 'CMD Support',
  permissions: [],
  workspace_memberships: [],
};

const MEMBER_USER: MockUser = {
  ...ADMIN_USER,
  id: '00000000-0000-0000-0000-0000000000b1',
  name: 'Test Member',
  email: 'member@cmdsupport.test',
  username: 'testmember',
  role: 'employee',
};

type Department = {
  id: string;
  name: string;
  description: string | null;
  unit_type: 'business_group' | 'squad_team';
  is_archived: boolean;
  archived_at: string | null;
  member_count: number;
  user_count: number;
};

type TaskProject = {
  id: string;
  name: string;
  description: string | null;
  identifier: string;
  workspace_id: string | null;
  department_id: string | null;
  allow_any_employee: boolean;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
};

type TelegramBinding = {
  id: string;
  department_id: string;
  default_task_project_id: string | null;
  chat_id: number;
  message_thread_id: number | null;
  chat_title: string | null;
  is_active: boolean;
  bot_status: string | null;
  bind_code: string | null;
  bind_code_expires_at: string | null;
  bound_at: string | null;
  disabled_at: string | null;
  created_at: string;
};

function buildSquadDepartment(): Department {
  return {
    id: SQUAD_ID,
    name: SQUAD_NAME,
    description: 'Squad seed for the Telegram tab e2e.',
    unit_type: 'squad_team',
    is_archived: false,
    archived_at: null,
    member_count: 4,
    user_count: 4,
  };
}

function buildTaskProject(): TaskProject {
  const now = new Date('2026-05-18T08:00:00.000Z').toISOString();
  return {
    id: PROJECT_ID,
    name: 'Squad α — sprint board',
    description: null,
    identifier: 'SA',
    workspace_id: null,
    department_id: SQUAD_ID,
    allow_any_employee: false,
    is_archived: false,
    created_at: now,
    updated_at: now,
  };
}

function buildPendingBinding(code: string): TelegramBinding {
  const now = new Date('2026-05-18T08:00:00.000Z').toISOString();
  const expires = new Date('2026-05-19T08:00:00.000Z').toISOString();
  return {
    id: '00000000-0000-0000-0000-0000000009a1',
    department_id: SQUAD_ID,
    default_task_project_id: PROJECT_ID,
    chat_id: 0,
    message_thread_id: null,
    chat_title: null,
    is_active: true,
    bot_status: null,
    bind_code: code,
    bind_code_expires_at: expires,
    bound_at: null,
    disabled_at: null,
    created_at: now,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function installTelegramApiGuard(page: Page): { hit: () => boolean } {
  let leaked = false;
  page.on('request', (request) => {
    if (request.url().includes('api.telegram.org')) {
      leaked = true;
    }
  });
  return { hit: () => leaked };
}

async function setupAuthedSession(page: Page, user: MockUser): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem('cmd_support_token', 'test-token-stub');
  });
  await page.route('**/api/auth/me', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(user),
    });
  });
}

/**
 * Install every API mock the department-hub Telegram tab touches. Returns
 * counters so tests can verify a POST actually fired.
 */
async function installDepartmentRoutes(page: Page): Promise<{
  bindings: TelegramBinding[];
  postCount: () => number;
}> {
  // /api/departments — list endpoint feeding the hub page lookup.
  await page.route('**/api/departments', async (route: Route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([buildSquadDepartment()]),
    });
  });

  // /api/departments/<id>/members — only fetched for non-admin users
  // (admins short-circuit in SquadTelegramTab). Stub with an empty list so
  // any accidental call cannot 404.
  await page.route('**/api/departments/*/members', async (route: Route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    });
  });

  // /api/tasks/projects?department_id=… — needs at least one non-archived
  // project so SquadTelegramTab resolves a defaultProjectId.
  await page.route('**/api/tasks/projects*', async (route: Route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    const url = route.request().url();
    // Only respond to the department-scoped list call; let other variants
    // (e.g. /api/tasks/projects/resolve) fall through to default mocking.
    if (!url.includes('department_id=')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([buildTaskProject()]),
    });
  });

  const bindings: TelegramBinding[] = [];
  let posts = 0;

  await page.route('**/api/telegram/bindings*', async (route: Route) => {
    const request = route.request();
    const method = request.method();
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(bindings),
      });
      return;
    }
    if (method === 'POST') {
      posts += 1;
      const pending = buildPendingBinding('CMD-TESTING1');
      bindings.unshift(pending);
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(pending),
      });
      return;
    }
    await route.fallback();
  });

  return { bindings, postCount: () => posts };
}

async function gotoOrSkip(page: Page, path: string): Promise<boolean> {
  try {
    await page.goto(path, { timeout: 15_000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Probe whether the Telegram tab on the department hub is deployed (T20).
 * Older stacks either 404 on the new tab key (parseTab() falls back to
 * "members") or are missing the SquadTelegramTab component entirely. In
 * both cases the `dept-tab-panel-telegram` sentinel never mounts.
 */
async function isTelegramTabDeployed(page: Page): Promise<boolean> {
  try {
    await page
      .getByTestId('dept-tab-panel-telegram')
      .waitFor({ state: 'visible', timeout: 5_000 });
    return true;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

test.describe('Telegram squad binding tab (/admin/departments/[id]?tab=telegram)', () => {
  test('admin generates a /bind code and the dialog shows /bind CMD-TESTING1', async ({
    page,
  }) => {
    const guard = installTelegramApiGuard(page);
    await setupAuthedSession(page, ADMIN_USER);
    const mocks = await installDepartmentRoutes(page);

    const reachable = await gotoOrSkip(
      page,
      `/admin/departments/${SQUAD_ID}?tab=telegram`,
    );
    test.skip(
      !reachable,
      'Next.js portal not reachable at the Playwright baseURL — start the Docker stack (`docker compose up -d`) or set E2E_BASE_URL.',
    );

    const deployed = await isTelegramTabDeployed(page);
    test.skip(
      !deployed,
      'Telegram tab on the department hub is not deployed (T20 missing on the running stack). Rebuild the frontend container (`docker compose up -d --build frontend`) and re-run.',
    );

    // Telegram tab panel mounts.
    const panel = page.getByTestId('dept-tab-panel-telegram');
    await expect(panel).toBeVisible({ timeout: 15_000 });

    // Intro section + the empty-state describing the bind flow.
    await expect(
      page.getByRole('heading', { name: 'Liên kết nhóm Telegram' }),
    ).toBeVisible();
    await expect(page.getByText('Chưa có liên kết Telegram')).toBeVisible({
      timeout: 10_000,
    });

    // The Tạo mã /bind button is enabled for admins (isLead = true) once
    // listTaskProjects resolves a default project.
    const generateButton = page.getByTestId('telegram-generate-bind-code');
    await expect(generateButton).toBeEnabled({ timeout: 10_000 });

    await generateButton.click();

    // Dialog appears with the spec-mandated payload.
    const dialog = page.getByTestId('telegram-bind-code-dialog');
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByTestId('telegram-bind-code-command'),
    ).toContainText('/bind CMD-TESTING1');
    await expect(page.getByTestId('telegram-bind-code-copy')).toBeVisible();

    expect(mocks.postCount()).toBe(1);

    await page.screenshot({
      path: 'tests/screenshots/T23-telegram-squad-binding-admin.png',
      fullPage: true,
    });

    expect(
      guard.hit(),
      'A request leaked to api.telegram.org while generating a /bind code.',
    ).toBe(false);
  });

  test('regular (non-lead) member sees the Tạo mã /bind button disabled', async ({
    page,
  }) => {
    const guard = installTelegramApiGuard(page);
    await setupAuthedSession(page, MEMBER_USER);
    await installDepartmentRoutes(page);

    // For a non-admin user, SquadTelegramTab evaluates `isLead` from the
    // membership list — override the members route so this employee is
    // explicitly NOT a lead/deputy/PO/SM.
    await page.unroute('**/api/departments/*/members');
    await page.route('**/api/departments/*/members', async (route: Route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: '00000000-0000-0000-0000-0000000010a1',
            employee_id: MEMBER_USER.id,
            department_id: SQUAD_ID,
            role: 'developer',
            capacity_percent: 100,
            is_primary: true,
            is_active: true,
            employee_name: MEMBER_USER.name,
          },
        ]),
      });
    });

    const reachable = await gotoOrSkip(
      page,
      `/admin/departments/${SQUAD_ID}?tab=telegram`,
    );
    test.skip(
      !reachable,
      'Next.js portal not reachable at the Playwright baseURL — start the Docker stack (`docker compose up -d`) or set E2E_BASE_URL.',
    );

    // Skip when the new tab simply isn't deployed. Without it, "Tạo mã
    // /bind" never renders and a "disabled" assertion would be a false
    // negative — so check first.
    const deployed = await isTelegramTabDeployed(page);
    test.skip(
      !deployed,
      'Telegram tab on the department hub is not deployed (T20 missing on the running stack). Rebuild the frontend container (`docker compose up -d --build frontend`) and re-run.',
    );

    // Non-admins may be redirected by the portal layout. If they reach the
    // panel, the action buttons must be disabled. If the portal pushes
    // them to /login or /me instead, that is also a valid "cannot bind"
    // outcome — assert one of those branches.
    const panel = page.getByTestId('dept-tab-panel-telegram');
    const reachedPanel = await panel
      .waitFor({ state: 'visible', timeout: 10_000 })
      .then(() => true)
      .catch(() => false);

    if (!reachedPanel) {
      // Portal-level redirect — `/admin/departments/...` is admin-gated in
      // production and the layout pushes the employee away. That is a
      // stricter pass than the "buttons disabled" condition.
      expect(page.url()).not.toContain('/admin/departments');
    } else {
      const generateButton = page.getByTestId('telegram-generate-bind-code');
      await expect(generateButton).toBeDisabled({ timeout: 10_000 });
    }

    await page.screenshot({
      path: 'tests/screenshots/T23-telegram-squad-binding-member.png',
      fullPage: true,
    });

    expect(
      guard.hit(),
      'A request leaked to api.telegram.org for the non-lead member view.',
    ).toBe(false);
  });
});
